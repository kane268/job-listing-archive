(() => {
  const storageKey = 'kane:job-archive-manage';
  const parameterName = 'manage';

  const readMode = () => {
    try {
      return window.localStorage.getItem(storageKey) === '1';
    } catch {
      return false;
    }
  };

  const setMode = isEnabled => {
    try {
      if (isEnabled) {
        window.localStorage.setItem(storageKey, '1');
      } else {
        window.localStorage.removeItem(storageKey);
      }
    } catch {
      // localStorage can fail in restricted browser contexts.
    }
  };

  const removeManageParameter = url => {
    url.searchParams.delete(parameterName);
    const query = url.searchParams.toString();
    return `${url.pathname}${query ? `?${query}` : ''}${url.hash}`;
  };

  const currentUrl = new URL(window.location.href);
  const manageParameter = currentUrl.searchParams.get(parameterName);
  if (['1', 'true', 'on'].includes((manageParameter || '').toLowerCase())) {
    setMode(true);
  } else if (['0', 'false', 'off'].includes((manageParameter || '').toLowerCase())) {
    setMode(false);
  }

  if (manageParameter !== null) {
    window.history.replaceState(window.history.state, '', removeManageParameter(currentUrl));
  }

  if (readMode()) {
    document.body.classList.add('is-owner-mode');
  }
})();
