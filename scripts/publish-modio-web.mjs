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
  ["xboxseriesx", "XBOX Series X/S"],
  ["ps5", "PlayStation 5"],
]);

const adminUrl = `https://mod.io/g/${gameSlug}/m/${modSlug}/admin/settings#files`;
const discussionUrl = `https://mod.io/g/${gameSlug}/m/${modSlug}#discussion`;

function sleep(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

async function waitFor(description, operation, interval = 750) {
  const deadline = Date.now() + timeoutSeconds * 1000;
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

async function readModioSessionState() {
  return evaluate(`(() => {
    const text = document.body?.innerText || '';
    const normalizedText = text.toLowerCase();
    return {
      ready: location.href.includes('/admin/settings') &&
        text.includes('File manager') &&
        text.includes('Admin'),
      loginRequired: normalizedText.includes('log in') ||
        normalizedText.includes('sign in') ||
        normalizedText.includes('войти') ||
        /\\/(login|signin)(?:[/?#]|$)/i.test(location.href),
      loginRoute: /\\/(login|signin)(?:[/?#]|$)/i.test(location.pathname),
      host: location.hostname
    };
  })`);
}

async function clickVisibleLarianSsoAction() {
  return evaluate(`(() => {
    const visible = (element) => {
      const style = getComputedStyle(element);
      const bounds = element.getBoundingClientRect();
      return style.visibility !== 'hidden' && style.display !== 'none' &&
        Number(style.opacity) !== 0 && bounds.width > 0 && bounds.height > 0 &&
        !element.disabled;
    };
    const selected = [...document.querySelectorAll('a, button, [role="button"]')]
      .filter(visible)
      .find((element) => {
        const label = [element.innerText, element.textContent, element.getAttribute('aria-label'), element.title]
          .filter(Boolean).join(' ').replace(/\\s+/g, ' ').trim();
        return /^(?:log|sign)\\s+in\\s+with\\s+larian(?:\\s+studios)?$/i.test(label);
      });
    if (!selected) return false;
    selected.click();
    return true;
  })`);
}

async function clickLarianAuthorizationAction() {
  return evaluate(`(() => {
    const visible = (element) => {
      const style = getComputedStyle(element);
      const bounds = element.getBoundingClientRect();
      return style.visibility !== 'hidden' && style.display !== 'none' &&
        Number(style.opacity) !== 0 && bounds.width > 0 && bounds.height > 0 &&
        !element.disabled;
    };
    const selected = [...document.querySelectorAll('a, button, [role="button"]')]
      .filter(visible)
      .find((element) => {
        const label = (element.innerText || element.textContent || '').replace(/\\s+/g, ' ').trim();
        return /^(continue|authorize|allow|confirm|proceed|продолжить|разрешить|подтвердить)$/i.test(label) ||
          /^(continue|authorize|allow access|продолжить|разрешить|предоставить доступ)$/i.test(label);
      });
    if (!selected) return false;
    selected.click();
    return true;
  })`);
}

async function recoverModioSessionWithLarian() {
  console.log('[publish-modio-web] mod.io session is signed out; trying the saved Larian SSO session.');
  const currentState = await readModioSessionState().catch(() => null);
  if (currentState?.loginRoute) {
    await call("Page.navigate", { url: discussionUrl });
    await waitFor("public mod discussion with the Larian sign-in action", async () =>
      evaluate(`(() => [...document.querySelectorAll('a, button, [role="button"]')].some((element) => {
        const style = getComputedStyle(element);
        const bounds = element.getBoundingClientRect();
        const label = [element.innerText, element.textContent, element.getAttribute('aria-label'), element.title]
          .filter(Boolean).join(' ').replace(/\\s+/g, ' ').trim();
        return style.visibility !== 'hidden' && style.display !== 'none' &&
          Number(style.opacity) !== 0 && bounds.width > 0 && bounds.height > 0 &&
          !element.disabled && /^(?:log|sign)\\s+in\\s+with\\s+larian(?:\\s+studios)?$/i.test(label);
      }))`),
    );
  }

  if (!await clickVisibleLarianSsoAction()) {
    throw new Error('mod.io is signed out and the public mod page has no visible Larian sign-in action.');
  }

  const deadline = Date.now() + timeoutSeconds * 1000;
  let lastState = null;
  let lastActionAt = Date.now();
  while (Date.now() < deadline) {
    await sleep(1000);
    lastState = await readModioSessionState().catch(() => null);
    if (lastState?.ready) {
      console.log('[publish-modio-web] mod.io session was restored through Larian SSO.');
      return;
    }

    const pageState = await evaluate(`(() => ({
      host: location.hostname,
      hasPasswordField: Boolean(document.querySelector('input[type="password"]')),
      loginRoute: /\\/(login|signin)(?:[/?#]|$)/i.test(location.pathname)
    }))`).catch(() => null);
    if (!pageState) continue;

    if (/larian\\.com$/i.test(pageState.host) && pageState.hasPasswordField) {
      throw new Error('The saved Larian browser session is not authenticated; the pre-job recovery hook must restore it before mod.io publication.');
    }

    if (Date.now() - lastActionAt < 3000) continue;
    if (/larian\\.com$/i.test(pageState.host)) {
      if (await clickLarianAuthorizationAction()) lastActionAt = Date.now();
      continue;
    }

    if (/mod\\.io$/i.test(pageState.host) && !pageState.loginRoute) {
      await call("Page.navigate", { url: adminUrl });
    }
  }

  throw new Error('Timed out restoring the mod.io session through Larian SSO. Last state: ' + JSON.stringify(lastState));
}

try {
  await call("Page.navigate", { url: adminUrl });
  let sessionState = await waitFor("mod.io session state", async () => {
    const state = await readModioSessionState();
    return state?.ready || state?.loginRequired ? state : null;
  });
  if (sessionState.loginRequired) {
    await recoverModioSessionWithLarian();
    await call("Page.navigate", { url: adminUrl });
    sessionState = await waitFor("authenticated mod.io file manager after Larian SSO recovery", async () => {
      const state = await readModioSessionState();
      return state?.ready ? state : null;
    });
  }
  if (!sessionState.ready) {
    throw new Error('mod.io browser session preflight did not reach the authenticated file manager: ' + JSON.stringify(sessionState) + '.');
  }

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
    let notReadyPolls = 0;
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
      })()`).catch(() => null).then(async (state) => {
        if (state?.editAvailable) {
          return state;
        }
        notReadyPolls += 1;
        if (notReadyPolls % 10 === 0) {
          await call("Page.reload", { ignoreCache: true });
        }
        return null;
      }),
      1500,
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
        const marker = [...document.querySelectorAll('div, span')]
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

    if (whatIf) {
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
      const selectionRequest = await evaluate(`(() => {
        const marker = [...document.querySelectorAll('div, span')]
          .find((item) => item.textContent.trim() === 'File ID: ${fileId}');
        const editor = marker?.closest('.tw-space-y-4.tw-relative');
        if (!editor) return { error: 'editor_missing' };
        const requested = ${JSON.stringify(desiredLabels)};
        const found = [];
        let changed = false;
        for (const label of [...editor.querySelectorAll('label')]) {
          const name = label.innerText.trim().split('\\n')[0];
          if (!requested.includes(name)) continue;
          const input = label.querySelector('input[type="checkbox"]');
          if (!input) return { error: 'checkbox_missing', name };
          found.push(name);
          if (!input.checked) {
            if (input.disabled) return { error: 'checkbox_disabled', name };
            input.click();
            changed = true;
          }
        }
        return { changed, found };
      })()`);
      if (selectionRequest.error) {
        throw new Error(`Platform selection failed: ${JSON.stringify(selectionRequest)}.`);
      }
      const absentPlatforms = desiredLabels.filter(
        (label) => !selectionRequest.found.includes(label),
      );
      if (absentPlatforms.length > 0) {
        throw new Error(`Platform controls are missing: ${absentPlatforms.join(", ")}.`);
      }

      const selection = await waitFor("requested platform selection to settle", async () =>
        evaluate(`(() => {
          const marker = [...document.querySelectorAll('div, span')]
            .find((item) => item.textContent.trim() === 'File ID: ${fileId}');
          const editor = marker?.closest('.tw-space-y-4.tw-relative');
          if (!editor) return null;
          const requested = ${JSON.stringify(desiredLabels)};
          const result = [...editor.querySelectorAll('label')]
            .map((label) => {
              const name = label.innerText.trim().split('\\n')[0];
              const input = label.querySelector('input[type="checkbox"]');
              return { name, checked: Boolean(input?.checked), disabled: Boolean(input?.disabled) };
            })
            .filter((item) => requested.includes(item.name));
          const complete = requested.every((name) =>
            result.some((item) => item.name === name && item.checked));
          return complete ? { result } : null;
        })()`),
        250,
      );
      selection.changed = selectionRequest.changed;

      let publishTriggered = false;
      if (selection.changed) {
        const saveAction = await waitFor("enabled Save button", async () =>
          evaluate(`(() => {
            const marker = [...document.querySelectorAll('div, span')]
              .find((item) => item.textContent.trim() === 'File ID: ${fileId}');
            const container = marker?.closest('.tw-space-y-4.tw-relative')?.parentElement;
            const button = [...(container?.querySelectorAll('button') || [])]
              .find((item) => ['Save', 'Save & publish'].includes(item.innerText.trim()));
            if (!button || button.disabled) return false;
            const action = button.innerText.trim();
            button.click();
            return action;
          })()`),
        );

        if (saveAction === "Save & publish") {
          publishTriggered = true;
        } else {
          await sleep(1500);
          const savedState = await waitFor("saved platform selection", async () =>
            evaluate(`(() => {
              const marker = [...document.querySelectorAll('div, span')]
                .find((item) => item.textContent.trim() === 'File ID: ${fileId}');
              if (!marker) return { closed: true };
              const editor = marker.closest('.tw-space-y-4.tw-relative');
              const container = editor?.parentElement;
              const requested = ${JSON.stringify(desiredLabels)};
              const selectedLabels = [...(editor?.querySelectorAll('label') || [])]
                .filter((label) => requested.includes(label.innerText.trim().split('\\n')[0]));
              const selected = selectedLabels.length === requested.length &&
                selectedLabels.every((label) => label.querySelector('input[type="checkbox"]')?.checked);
              const saveButton = [...(container?.querySelectorAll('button') || [])]
                .find((item) => ['Save', 'Save & publish'].includes(item.innerText.trim()));
              return selected && saveButton?.disabled ? { closed: false } : false;
            })()`),
          );

          if (!savedState.closed) {
            await evaluate(`(() => {
              const marker = [...document.querySelectorAll('div, span')]
                .find((item) => item.textContent.trim() === 'File ID: ${fileId}');
              const container = marker?.closest('.tw-space-y-4.tw-relative')?.parentElement;
              const button = [...(container?.querySelectorAll('button') || [])]
                .find((item) => item.innerText.trim() === 'Cancel');
              button?.click();
              return true;
            })()`);
            await waitFor("file editor to close", async () =>
              evaluate(`(() => ![...document.querySelectorAll('div, span')]
                .some((item) => item.textContent.trim() === 'File ID: ${fileId}'))()`),
            );
          }
        }
      } else {
        await evaluate(`(() => {
          const marker = [...document.querySelectorAll('div, span')]
            .find((item) => item.textContent.trim() === 'File ID: ${fileId}');
          const container = marker?.closest('.tw-space-y-4.tw-relative')?.parentElement;
          const button = [...(container?.querySelectorAll('button') || [])]
            .find((item) => item.innerText.trim() === 'Cancel');
          button?.click();
          return true;
        })()`);
      }

      if (!publishTriggered) {
        await call("Page.reload", { ignoreCache: true });
        await waitFor("enabled Publish button", async () =>
          evaluate(`(() => {
            const row = [...document.querySelectorAll('a')]
              .find((item) => item.href.includes('/files/${fileId}/download'))?.closest('tr');
            const button = [...(row?.querySelectorAll('button') || [])]
              .find((item) => item.innerText.trim() === 'Publish');
            if (!button || button.disabled) return false;
            button.click();
            return true;
          })()`),
        );
      }

      await waitFor("Confirm publish dialog", async () =>
        evaluate(`(() => {
          const button = [...document.querySelectorAll('button')]
            .find((item) => item.innerText.trim() === 'Confirm publish');
          if (!button || button.disabled) return false;
          button.click();
          return true;
        })()`),
      );

      await waitFor("published file state", async () =>
        evaluate(`(() => {
          const row = [...document.querySelectorAll('a')]
            .find((item) => item.href.includes('/files/${fileId}/download'))?.closest('tr');
          const button = [...(row?.querySelectorAll('button') || [])]
            .find((item) => item.innerText.trim() === 'Publish');
          return Boolean(row && button?.disabled);
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

