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

async function waitFor(description, operation, interval = 750, maxSeconds = timeoutSeconds) {
  const deadline = Date.now() + maxSeconds * 1000;
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

const targets = await fetch(`http://127.0.0.1:${debugPort}/json/list`, {
  signal: AbortSignal.timeout(10_000),
}).then((response) => {
  if (!response.ok) {
    throw new Error(`CDP target list returned HTTP ${response.status}.`);
  }
  return response.json();
});
const modioTargets = targets.filter((candidate) => {
  if (candidate.type !== "page") return false;
  try {
    const url = new URL(candidate.url);
    return url.protocol === "https:" && url.hostname === "mod.io" && (url.port === "" || url.port === "443");
  } catch {
    return false;
  }
});
if (modioTargets.length !== 1) {
  throw new Error(`Expected exactly one HTTPS mod.io browser page; found ${modioTargets.length}.`);
}
const target = modioTargets[0];
const CDP_REQUEST_TIMEOUT_MS = 10_000;
const socket = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve, reject) => {
  let settled = false;
  const finish = (error) => {
    if (settled) return;
    settled = true;
    clearTimeout(timer);
    socket.removeEventListener("open", onOpen);
    socket.removeEventListener("error", onError);
    socket.removeEventListener("close", onClose);
    if (error) reject(error);
    else resolve();
  };
  const onOpen = () => finish();
  const onError = () => finish(new Error("CDP WebSocket failed to open."));
  const onClose = () => finish(new Error("CDP WebSocket closed before opening."));
  const timer = setTimeout(() => {
    finish(new Error("Timed out opening CDP WebSocket."));
    try { socket.close(); } catch {}
  }, CDP_REQUEST_TIMEOUT_MS);
  socket.addEventListener("open", onOpen, { once: true });
  socket.addEventListener("error", onError, { once: true });
  socket.addEventListener("close", onClose, { once: true });
});

let nextId = 1;
const pending = new Map();

function rejectPendingRequests(message) {
  for (const [id, request] of pending) {
    clearTimeout(request.timer);
    pending.delete(id);
    request.reject(new Error(message));
  }
}

socket.addEventListener("message", (event) => {
  let message;
  try {
    message = JSON.parse(event.data);
  } catch {
    rejectPendingRequests("Invalid CDP response.");
    return;
  }
  if (!message.id || !pending.has(message.id)) return;
  const request = pending.get(message.id);
  pending.delete(message.id);
  clearTimeout(request.timer);
  if (message.error) request.reject(new Error("CDP request failed."));
  else request.resolve(message.result);
});
socket.addEventListener("error", () => rejectPendingRequests("CDP WebSocket error."));
socket.addEventListener("close", () => rejectPendingRequests("CDP WebSocket closed."));

function call(method, params = {}) {
  const id = nextId++;
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      pending.delete(id);
      const error = new Error("CDP request timed out.");
      error.code = "cdp_timeout";
      reject(error);
    }, CDP_REQUEST_TIMEOUT_MS);
    pending.set(id, { resolve, reject, timer });
    try {
      socket.send(JSON.stringify({ id, method, params }));
    } catch {
      clearTimeout(timer);
      pending.delete(id);
      reject(new Error("CDP request could not be sent."));
    }
  });
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
  return evaluate(String.raw`(() => {
    const url = new URL(location.href);
    const expectedModPath = '/g/baldursgate3/m/dnd-55e-all-in-one-beyond-russian-localization';
    const expectedAdminPath = expectedModPath + '/admin/settings';
    const onModio = url.protocol === 'https:' && url.hostname === 'mod.io' &&
      (url.port === '' || url.port === '443');
    const modPath = url.pathname === expectedModPath || url.pathname.startsWith(expectedModPath + '/');
    const gamePortalRoute = url.pathname === '/g/baldursgate3';
    const loginRoute = /(?:^|\/)(?:login|signin)(?:\/|$)/i.test(url.pathname);
    const pageText = document.body?.innerText || '';
    const visible = (element) => {
      const style = getComputedStyle(element);
      const bounds = element.getBoundingClientRect();
      return style.visibility !== 'hidden' && style.display !== 'none' &&
        Number(style.opacity) !== 0 && bounds.width > 0 && bounds.height > 0 &&
        !element.disabled && element.getAttribute('aria-disabled') !== 'true';
    };
    const labelsOf = (element) => [element.innerText, element.textContent,
      element.getAttribute('aria-label'), element.title]
      .filter(Boolean).map((value) => String(value).replace(/\s+/g, ' ').trim()).filter(Boolean);
    return {
      ready: onModio && url.pathname === expectedAdminPath &&
        pageText.includes('File manager') && pageText.includes('Admin'),
      loginRequired: onModio && (loginRoute || ((modPath || gamePortalRoute) &&
        [...document.querySelectorAll('a, button, [role="button"]')].some((element) =>
          visible(element) && labelsOf(element).some((label) => /^(?:log in|sign in|войти)$/i.test(label))
        ))),
      loginRoute,
      host: onModio ? 'mod.io' : 'other'
    };
  })()`);
}

async function readLoginActionState() {
  return evaluate(String.raw`(() => {
    const url = new URL(location.href);
    const expectedModPath = '/g/baldursgate3/m/dnd-55e-all-in-one-beyond-russian-localization';
    const onModio = url.protocol === 'https:' && url.hostname === 'mod.io' &&
      (url.port === '' || url.port === '443');
    const modPath = url.pathname === expectedModPath || url.pathname.startsWith(expectedModPath + '/');
    const loginRoute = url.pathname === '/login' || url.pathname === '/signin';
    const gamePortalRoute = url.pathname === '/g/baldursgate3';
    const expectedContext = onModio && (modPath || loginRoute || gamePortalRoute);
    const genericPattern = /^(?:log in|sign in|войти)$/i;
    const ssoPattern = /^(?:log in|sign in) with larian(?: studios)?$|^link your larian studios account$/i;

    const labelsOf = (element) => [element.innerText, element.textContent,
      element.getAttribute('aria-label'), element.title]
      .filter(Boolean).map((value) => String(value).replace(/\s+/g, ' ').trim()).filter(Boolean);
    const isVisible = (element) => {
      const style = getComputedStyle(element);
      const bounds = element.getBoundingClientRect();
      return style.visibility !== 'hidden' && style.display !== 'none' &&
        Number(style.opacity) !== 0 && bounds.width > 0 && bounds.height > 0;
    };
    const inspect = (elements, pattern, countUnsafeTarget) => {
      const counts = {
        matchingLabels: 0,
        hiddenOrOutOfBounds: 0,
        disabled: 0,
        ariaDisabled: 0,
        unsafeSsoTarget: 0
      };
      let eligible = 0;
      for (const element of elements) {
        if (!labelsOf(element).some((label) => pattern.test(label))) continue;
        counts.matchingLabels++;
        if (!isVisible(element)) {
          counts.hiddenOrOutOfBounds++;
          continue;
        }
        if (element.disabled) {
          counts.disabled++;
          continue;
        }
        if (element.getAttribute('aria-disabled') === 'true') {
          counts.ariaDisabled++;
          continue;
        }
        if (countUnsafeTarget) {
          const linkAction = gamePortalRoute && labelsOf(element).some((label) => /^link your larian studios account$/i.test(label));
          const href = element.getAttribute('href');
          if (linkAction && !href) {
            // The exact, visible BG3 portal button is the documented linking action.
          } else {
            let target;
            try { target = new URL(href || element.href); } catch {
              counts.unsafeSsoTarget++;
              continue;
            }
            const allowedHost = linkAction
              ? target.hostname === 'mod.io' || target.hostname.endsWith('.mod.io') || target.hostname === 'larian.com' || target.hostname.endsWith('.larian.com')
              : target.hostname === 'larian.com' || target.hostname.endsWith('.larian.com');
            if (target.protocol !== 'https:' || !allowedHost || !(target.port === '' || target.port === '443')) {
              counts.unsafeSsoTarget++;
              continue;
            }
          }
        }
        eligible++;
      }
      return { eligible, counts };
    };

    const generic = expectedContext && (modPath || loginRoute || gamePortalRoute)
      ? inspect([...document.querySelectorAll('a, button, [role="button"]')], genericPattern, false)
      : { eligible: 0, counts: { matchingLabels: 0, hiddenOrOutOfBounds: 0, disabled: 0, ariaDisabled: 0, unsafeSsoTarget: 0 } };
    const sso = onModio
      ? inspect([...document.querySelectorAll('a[href], button, [role="button"]')], ssoPattern, true)
      : { eligible: 0, counts: { matchingLabels: 0, hiddenOrOutOfBounds: 0, disabled: 0, ariaDisabled: 0, unsafeSsoTarget: 0 } };

    const larianHost = url.protocol === 'https:' &&
      (url.hostname === 'larian.com' || url.hostname.endsWith('.larian.com')) &&
      (url.port === '' || url.port === '443');
    const visibleApproval = (element) => {
      const style = getComputedStyle(element);
      const bounds = element.getBoundingClientRect();
      return style.visibility !== 'hidden' && style.display !== 'none' &&
        Number(style.opacity) !== 0 && bounds.width > 0 && bounds.height > 0 &&
        !element.disabled && element.getAttribute('aria-disabled') !== 'true';
    };
    const challenge = larianHost && Boolean(document.querySelector(
      'input[type="password"], input[autocomplete="one-time-code"], iframe[src*="captcha"], [class*="captcha"], [id*="captcha"]'
    ));
    const approvalRequired = larianHost && [...document.querySelectorAll('button, [role="button"]')]
      .some((element) => visibleApproval(element) &&
        labelsOf(element).some((label) =>
          /^(?:continue|authorize|allow|confirm|proceed|продолжить|разрешить|подтвердить)$/i.test(label)
        ));
    return {
      expectedContext,
      genericCount: generic.eligible,
      ssoCount: sso.eligible,
      genericRejections: generic.counts,
      ssoRejections: sso.counts,
      larianHost,
      challenge,
      approvalRequired
    };
  })()`);
}

async function clickGenericModioLoginAction() {
  return evaluate(String.raw`(() => {
    const url = new URL(location.href);
    const expectedModPath = '/g/baldursgate3/m/dnd-55e-all-in-one-beyond-russian-localization';
    const gamePortalRoute = url.pathname === '/g/baldursgate3';
    const expectedPath = url.pathname === expectedModPath ||
      url.pathname.startsWith(expectedModPath + '/') ||
      url.pathname === '/login' ||
      url.pathname === '/signin' || gamePortalRoute;
    if (url.protocol !== 'https:' || url.hostname !== 'mod.io' ||
        !(url.port === '' || url.port === '443') || !expectedPath) return 'wrong_context';
    const visible = (element) => {
      const style = getComputedStyle(element);
      const bounds = element.getBoundingClientRect();
      return style.visibility !== 'hidden' && style.display !== 'none' &&
        Number(style.opacity) !== 0 && bounds.width > 0 && bounds.height > 0 &&
        !element.disabled && element.getAttribute('aria-disabled') !== 'true';
    };
    const labelsOf = (element) => [element.innerText, element.textContent,
      element.getAttribute('aria-label'), element.title]
      .filter(Boolean).map((value) => String(value).replace(/\s+/g, ' ').trim()).filter(Boolean);
    const matches = [...document.querySelectorAll('a, button, [role="button"]')]
      .filter((element) => visible(element) &&
        labelsOf(element).some((label) => /^(?:log in|sign in|войти)$/i.test(label)));
    if (matches.length !== 1) return matches.length ? 'ambiguous' : 'missing';
    const anchor = matches[0];
    if (anchor instanceof HTMLAnchorElement) {
      let target;
      try { target = new URL(anchor.href, location.href); } catch { return 'invalid_target'; }
      if (target.protocol !== 'https:' || target.hostname !== 'mod.io' ||
          !(target.port === '' || target.port === '443')) return 'invalid_target';
      anchor.target = '_self';
    }
    matches[0].click();
    return 'clicked';
  })()`);
}

async function clickVisibleLarianSsoAction() {
  return evaluate(String.raw`(() => {
    const url = new URL(location.href);
    const expectedModPath = '/g/baldursgate3/m/dnd-55e-all-in-one-beyond-russian-localization';
    const modPath = url.pathname === expectedModPath || url.pathname.startsWith(expectedModPath + '/');
    const loginRoute = url.pathname === '/login' || url.pathname === '/signin';
    const gamePortalRoute = url.pathname === '/g/baldursgate3';
    if (url.protocol !== 'https:' || url.hostname !== 'mod.io' ||
        !(url.port === '' || url.port === '443')) return 'wrong_context';
    const visible = (element) => {
      const style = getComputedStyle(element);
      const bounds = element.getBoundingClientRect();
      return style.visibility !== 'hidden' && style.display !== 'none' &&
        Number(style.opacity) !== 0 && bounds.width > 0 && bounds.height > 0 &&
        !element.disabled && element.getAttribute('aria-disabled') !== 'true';
    };
    const labelsOf = (element) => [element.innerText, element.textContent,
      element.getAttribute('aria-label'), element.title]
      .filter(Boolean).map((value) => String(value).replace(/\s+/g, ' ').trim()).filter(Boolean);
    const matches = [...document.querySelectorAll('a[href], button, [role="button"]')].filter((element) =>
      visible(element) &&
      labelsOf(element).some((label) => /^(?:log in|sign in) with larian(?: studios)?$|^link your larian studios account$/i.test(label))
    );
    if (matches.length !== 1) return matches.length ? 'ambiguous' : 'missing';
    const linkAction = labelsOf(matches[0]).some((label) => /^link your larian studios account$/i.test(label));
    if (linkAction) {
      if (!gamePortalRoute) return 'wrong_context';
      const href = matches[0].getAttribute('href');
      if (href) {
        let target;
        try { target = new URL(href, location.href); } catch { return 'invalid_target'; }
        const allowedHost = target.hostname === 'mod.io' || target.hostname.endsWith('.mod.io') || target.hostname === 'larian.com' || target.hostname.endsWith('.larian.com');
        if (target.protocol !== 'https:' || !allowedHost || !(target.port === '' || target.port === '443')) return 'invalid_target';
      }
    } else {
      let target;
      try { target = new URL(matches[0].href); } catch { return 'invalid_target'; }
      if (target.protocol !== 'https:' ||
          !(target.hostname === 'larian.com' || target.hostname.endsWith('.larian.com')) ||
          !(target.port === '' || target.port === '443')) return 'invalid_target';
    }
    if (matches[0] instanceof HTMLAnchorElement) matches[0].target = '_self';
    matches[0].click();
    return 'clicked';
  })()`);
}

async function recoverModioSessionWithLarian() {
  console.log('[publish-modio-web] mod.io session is signed out; trying the saved Larian SSO session.');
  let currentState = await readModioSessionState().catch(() => null);
  if (!currentState?.ready || currentState?.host !== 'mod.io') {
    await call("Page.navigate", { url: `https://mod.io/g/${gameSlug}` });
  }
  let lastActionState = null;
  let lastReadErrorCategory = null;
  async function readLoginActionStateSafely() {
    try {
      const state = await readLoginActionState();
      lastReadErrorCategory = null;
      return state;
    } catch (error) {
      lastReadErrorCategory =
        error?.code === 'cdp_timeout' ? 'cdp_timeout' : 'cdp_read_failed';
      return null;
    }
  }
  const onlyHiddenGenericLogin = (state) =>
    state?.expectedContext &&
    state.genericCount === 0 &&
    state.ssoCount === 0 &&
    state.genericRejections?.matchingLabels === 1 &&
    state.genericRejections?.hiddenOrOutOfBounds === 1 &&
    state.genericRejections?.disabled === 0 &&
    state.genericRejections?.ariaDisabled === 0 &&
    !state.challenge &&
    !state.approvalRequired;

  let actionState = await waitFor('safe mod.io login action', async () => {
    lastActionState = await readLoginActionStateSafely();
    return lastActionState?.expectedContext &&
      (lastActionState.ssoCount > 0 ||
        lastActionState.genericCount > 0 ||
        lastActionState.challenge ||
        onlyHiddenGenericLogin(lastActionState))
      ? lastActionState : null;
  }, 500, Math.min(timeoutSeconds, 60)).catch(() => null);
  if (onlyHiddenGenericLogin(actionState)) {
    await call("Page.navigate", { url: `https://mod.io/g/${gameSlug}?portal=studio` });
    actionState = await waitFor(
      "safe login action on canonical mod.io login page",
      async () => {
        lastActionState = await readLoginActionStateSafely();
        return lastActionState?.expectedContext &&
          (lastActionState.ssoCount > 0 ||
            lastActionState.genericCount > 0 ||
            lastActionState.challenge ||
            lastActionState.approvalRequired)
          ? lastActionState : null;
      },
      500,
      Math.min(timeoutSeconds, 60),
    ).catch(() => null);
  }
  if (!actionState) {
    const diagnostic = {
      readErrorCategory: lastReadErrorCategory,
      ...(lastActionState ? {
        expectedContext: lastActionState.expectedContext,
        genericCount: lastActionState.genericCount,
        ssoCount: lastActionState.ssoCount,
        genericRejections: lastActionState.genericRejections,
        ssoRejections: lastActionState.ssoRejections,
        challenge: lastActionState.challenge,
        approvalRequired: lastActionState.approvalRequired
      } : {})
    };
    throw new Error('No unique safe mod.io login action became available: ' + JSON.stringify(diagnostic));
  }
  if (actionState.challenge) throw new Error('Larian authentication requires user action; automatic publication stopped safely.');
  if (actionState.ssoCount === 0) {
    const genericClick = await clickGenericModioLoginAction();
    if (genericClick !== 'clicked') throw new Error('A unique, safe mod.io login action was not available; automatic publication stopped.');
    actionState = await waitFor('Larian SSO action or redirect from the mod.io login page', async () => {
      const state = await readLoginActionStateSafely();
      return state?.larianHost ||
        (state?.ssoCount > 0 || (state?.expectedContext && (state.challenge || state.approvalRequired)))
        ? state : null;
    }, 500, Math.min(timeoutSeconds, 60)).catch(async () => {
      const state = await readLoginActionStateSafely();
      const diagnostic = state ? {
        expectedContext: state.expectedContext,
        genericCount: state.genericCount,
        ssoCount: state.ssoCount,
        larianHost: state.larianHost,
        challenge: state.challenge,
        approvalRequired: state.approvalRequired
      } : { readErrorCategory: lastReadErrorCategory };
      throw new Error('BG3 login transition did not expose an SSO action: ' + JSON.stringify(diagnostic));
    });
  }
  if (actionState.larianHost) {
    if (actionState.challenge) throw new Error('Larian authentication requires user action; automatic publication stopped safely.');
    if (actionState.approvalRequired) throw new Error('Larian requires an interactive approval; automatic publication stopped safely.');
    const returnedToModio = await waitFor('authenticated return from Larian to mod.io', async () => {
      const state = await readModioSessionState().catch(() => null);
      return state?.host === 'mod.io' && (state.ready || !state.loginRequired) ? state : null;
    }, 1000, timeoutSeconds).catch(() => null);
    if (!returnedToModio) {
      const finalState = await readLoginActionStateSafely();
      throw new Error('Larian SSO did not return to mod.io: ' + JSON.stringify({
        larianHost: finalState?.larianHost ?? false,
        challenge: finalState?.challenge ?? false,
        approvalRequired: finalState?.approvalRequired ?? false
      }));
    }
    console.log('[publish-modio-web] mod.io session was restored through the BG3 Larian portal.');
    return;
  }
  if (actionState.challenge) throw new Error('Larian authentication requires user action; automatic publication stopped safely.');
  if (actionState.approvalRequired) throw new Error('Larian requires an interactive approval; automatic publication stopped safely.');
  const ssoClick = await clickVisibleLarianSsoAction();
  if (ssoClick !== 'clicked') throw new Error('A unique, allowlisted Larian SSO action was not available; automatic publication stopped.');
  const deadline = Date.now() + timeoutSeconds * 1000;
  while (Date.now() < deadline) {
    await sleep(1000);
    currentState = await readModioSessionState().catch(() => null);
    if (currentState?.ready) {
      console.log('[publish-modio-web] mod.io session was restored through Larian SSO.');
      return;
    }
    actionState = await readLoginActionStateSafely();
    if (actionState?.challenge) throw new Error('Larian authentication requires user action; automatic publication stopped safely.');
    if (actionState?.approvalRequired) throw new Error('Larian requires an interactive approval; automatic publication stopped safely.');
    if (currentState?.host === 'mod.io' && !currentState.loginRequired) return;
  }
  throw new Error('Timed out restoring the mod.io session through Larian SSO.');
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

