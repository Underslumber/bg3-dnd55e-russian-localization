#!/usr/bin/env node

const args = new Map();
for (let index = 2; index < process.argv.length; index += 2) {
  args.set(process.argv[index], process.argv[index + 1] ?? "");
}

const fileId = Number(args.get("--file-id") || 0);
const modSlug =
  args.get("--mod-slug") ||
  "dnd-55e-all-in-one-beyond-russian-localization";
const gameSlug = args.get("--game-slug") || "baldursgate3";
const debugPort = Number(args.get("--debug-port") || 9222);
const timeoutSeconds = Number(args.get("--timeout-seconds") || 120);
const whatIf = (args.get("--what-if") || "false").toLowerCase() === "true";
const requestedPlatforms = (args.get("--platforms") || "windows,mac,xboxseriesx,ps5")
  .split(",")
  .map((value) => value.trim())
  .filter(Boolean);

const platformLabels = new Map([
  ["windows", "Windows"],
  ["mac", "Mac"],
  ["xboxseriesx", "Xbox Series X/S"],
  ["ps5", "PlayStation 5"],
]);

const adminUrl = `https://mod.io/g/${gameSlug}/m/${modSlug}/admin/settings#files`;
const deadline = Date.now() + timeoutSeconds * 1000;

function sleep(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

async function waitFor(description, operation, interval = 750) {
  let lastValue;
  while (Date.now() < deadline) {
    lastValue = await operation();
    if (lastValue) {
      return lastValue;
    }
    await sleep(interval);
  }
  throw new Error(`Timed out waiting for ${description}. Last value: ${JSON.stringify(lastValue)}`);
}

const targets = await fetch(`http://127.0.0.1:${debugPort}/json/list`).then((response) => {
  if (!response.ok) {
    throw new Error(`CDP target list returned HTTP ${response.status}.`);
  }
  return response.json();
});
const target =
  targets.find((candidate) => candidate.type === "page" && candidate.url.includes("mod.io")) ||
  targets.find((candidate) => candidate.type === "page");
if (!target) {
  throw new Error("No browser page is available through CDP.");
}

const socket = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve, reject) => {
  socket.addEventListener("open", resolve, { once: true });
  socket.addEventListener("error", reject, { once: true });
});

let nextId = 1;
const pending = new Map();
socket.addEventListener("message", (event) => {
  const message = JSON.parse(event.data);
  if (!message.id || !pending.has(message.id)) {
    return;
  }
  const { resolve, reject } = pending.get(message.id);
  pending.delete(message.id);
  if (message.error) {
    reject(new Error(JSON.stringify(message.error)));
  } else {
    resolve(message.result);
  }
});

function call(method, params = {}) {
  const id = nextId++;
  socket.send(JSON.stringify({ id, method, params }));
  return new Promise((resolve, reject) => pending.set(id, { resolve, reject }));
}

async function evaluate(expression) {
  const response = await call("Runtime.evaluate", {
    expression,
    returnByValue: true,
    awaitPromise: true,
  });
  if (response.exceptionDetails) {
    throw new Error(response.exceptionDetails.text || "Browser evaluation failed.");
  }
  return response.result.value;
}

try {
  await call("Page.navigate", { url: adminUrl });
  await waitFor("authenticated mod.io file manager", async () =>
    evaluate(`(() => ({
      ready: location.href.includes('/admin/settings') &&
        document.body.innerText.includes('File manager') &&
        document.body.innerText.includes('Admin'),
      loginRequired: document.body.innerText.includes('Log in') ||
        document.body.innerText.includes('Sign in')
    }))()`).then((state) => {
      if (state?.loginRequired) {
        throw new Error("The saved mod.io browser session is no longer authenticated.");
      }
      return state?.ready;
    }),
  );

  if (!fileId) {
    console.log(
      JSON.stringify({
        status: "whatif",
        authenticated: true,
        adminUrl,
        message: "Authenticated mod.io file manager is available; no file was changed.",
      }),
    );
    process.exitCode = 0;
  } else {
    const rowState = await waitFor(`mod.io file ${fileId}`, async () =>
      evaluate(`(() => {
        const anchor = [...document.querySelectorAll('a')]
          .find((item) => item.href.includes('/files/${fileId}/download'));
        const row = anchor?.closest('tr');
        if (!row) return null;
        const editButton = row.querySelector('svg[data-icon="pencil-alt"]')?.closest('button');
        const publishButton = [...row.querySelectorAll('button')]
          .find((button) => button.innerText.trim() === 'Publish');
        return {
          found: true,
          editAvailable: Boolean(editButton && !editButton.disabled),
          publishDisabled: Boolean(publishButton?.disabled),
          version: row.children[2]?.innerText.trim() || '',
          filename: row.children[0]?.innerText.trim() || ''
        };
      })()`),
    );

    if (!rowState.editAvailable) {
      throw new Error(`Edit control for mod.io file ${fileId} is unavailable.`);
    }

    await evaluate(`(() => {
      const row = [...document.querySelectorAll('a')]
        .find((item) => item.href.includes('/files/${fileId}/download'))?.closest('tr');
      row?.querySelector('svg[data-icon="pencil-alt"]')?.closest('button')?.click();
      return true;
    })()`);

    const editorState = await waitFor(`edit panel for file ${fileId}`, async () =>
      evaluate(`(() => {
        const marker = [...document.querySelectorAll('span')]
          .find((item) => item.textContent.trim() === 'File ID: ${fileId}');
        const editor = marker?.closest('.tw-space-y-4.tw-relative');
        if (!editor) return null;
        const container = editor.parentElement;
        const buttons = [...container.querySelectorAll('button')]
          .map((button) => ({ text: button.innerText.trim(), disabled: button.disabled }));
        const platforms = [...editor.querySelectorAll('label')]
          .map((label) => ({
            label: label.innerText.trim().split('\\n')[0],
            checked: Boolean(label.querySelector('input[type="checkbox"]')?.checked),
            disabled: Boolean(label.querySelector('input[type="checkbox"]')?.disabled)
          }))
          .filter((item) => item.label);
        return { buttons, platforms };
      })()`),
    );

    const desiredLabels = requestedPlatforms.map((platform) => {
      if (!platformLabels.has(platform)) {
        throw new Error(`Unsupported mod.io platform '${platform}'.`);
      }
      return platformLabels.get(platform);
    });

    const saveAndPublish = editorState.buttons.find(
      (button) => button.text === "Save & publish",
    );
    if (!saveAndPublish) {
      const allSelected = desiredLabels.every(
        (label) => editorState.platforms.find((platform) => platform.label === label)?.checked,
      );
      if (!allSelected) {
        throw new Error(
          `File ${fileId} has no Save & publish action and its platform selection is incomplete.`,
        );
      }
      console.log(
        JSON.stringify({
          status: "already_live",
          fileId,
          filename: rowState.filename,
          version: rowState.version,
          platforms: desiredLabels,
        }),
      );
      process.exitCode = 0;
    } else if (whatIf) {
      console.log(
        JSON.stringify({
          status: "whatif",
          authenticated: true,
          fileId,
          filename: rowState.filename,
          version: rowState.version,
          currentPlatforms: editorState.platforms,
          requestedPlatforms: desiredLabels,
          message: "The file can be finalized through the authenticated browser; no checkbox or button was changed.",
        }),
      );
      process.exitCode = 0;
    } else {
      const selection = await evaluate(`(() => {
        const marker = [...document.querySelectorAll('span')]
          .find((item) => item.textContent.trim() === 'File ID: ${fileId}');
        const editor = marker?.closest('.tw-space-y-4.tw-relative');
        if (!editor) return { error: 'editor_missing' };
        const requested = ${JSON.stringify(desiredLabels)};
        const result = [];
        for (const label of [...editor.querySelectorAll('label')]) {
          const name = label.innerText.trim().split('\\n')[0];
          if (!requested.includes(name)) continue;
          const input = label.querySelector('input[type="checkbox"]');
          if (!input) return { error: 'checkbox_missing', name };
          if (!input.checked) input.click();
          result.push({ name, checked: input.checked });
        }
        return { result };
      })()`);
      if (selection.error) {
        throw new Error(`Platform selection failed: ${JSON.stringify(selection)}.`);
      }

      await waitFor("enabled Save & publish button", async () =>
        evaluate(`(() => {
          const marker = [...document.querySelectorAll('span')]
            .find((item) => item.textContent.trim() === 'File ID: ${fileId}');
          const container = marker?.closest('.tw-space-y-4.tw-relative')?.parentElement;
          const button = [...(container?.querySelectorAll('button') || [])]
            .find((item) => item.innerText.trim() === 'Save & publish');
          if (!button || button.disabled) return false;
          button.click();
          return true;
        })()`),
      );

      await waitFor("Confirm publish dialog", async () =>
        evaluate(`(() => {
          const button = [...document.querySelectorAll('button')]
            .find((item) => item.innerText.trim() === 'Confirm publish');
          if (!button || button.disabled) return false;
          button.click();
          return true;
        })()`),
      );

      await waitFor("file manager after publish", async () =>
        evaluate(`(() => {
          const marker = [...document.querySelectorAll('span')]
            .find((item) => item.textContent.trim() === 'File ID: ${fileId}');
          return !marker && document.body.innerText.includes('File manager');
        })()`),
      );

      console.log(
        JSON.stringify({
          status: "published",
          fileId,
          filename: rowState.filename,
          version: rowState.version,
          platforms: desiredLabels,
        }),
      );
      process.exitCode = 0;
    }
  }
} finally {
  socket.close();
}
