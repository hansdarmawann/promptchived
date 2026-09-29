(() => {
  const script = document.currentScript;
  const dialog = document.querySelector("#folder-picker");
  const content = document.querySelector("#folder-picker-content");
  const input = document.querySelector("#source-root-path");
  const openButton = document.querySelector(".folder-picker-trigger");
  const closeButton = document.querySelector(".folder-picker-close");
  if (!dialog || !content || !input || !openButton || !closeButton) return;

  const messages = {
    empty: script.dataset.empty,
    error: script.dataset.error,
    up: script.dataset.up,
    select: script.dataset.select,
  };

  const element = (tag, text, className) => {
    const node = document.createElement(tag);
    node.textContent = text;
    if (className) node.className = className;
    return node;
  };

  const action = (text, path, kind = "open") => {
    const button = element("button", text, "secondary folder-action");
    button.type = "button";
    button.dataset.path = path;
    button.dataset.action = kind;
    return button;
  };

  const showError = () => {
    content.replaceChildren(element("p", messages.error, "notice"));
  };

  const render = (listing) => {
    const fragment = document.createDocumentFragment();
    if (!listing.path) {
      if (!listing.roots.length) {
        fragment.append(element("p", messages.empty, "muted"));
      } else {
        const roots = element("div", "", "folder-list");
        listing.roots.forEach((root) => roots.append(action(root.name, root.path)));
        fragment.append(roots);
      }
      content.replaceChildren(fragment);
      return;
    }

    const current = element("p", listing.path, "path folder-current-path");
    fragment.append(current, action(messages.select, listing.path, "select"));
    if (listing.parent) fragment.append(action(messages.up, listing.parent));

    const folders = element("div", "", "folder-list");
    listing.folders.forEach((folder) => folders.append(action(folder.name, folder.path)));
    fragment.append(folders);
    content.replaceChildren(fragment);
  };

  const load = async (path) => {
    content.replaceChildren(element("p", "…", "muted"));
    const url = path ? `/api/source-folders?path=${encodeURIComponent(path)}` : "/api/source-folders";
    try {
      const response = await fetch(url, { headers: { Accept: "application/json" } });
      if (!response.ok) throw new Error("Folder listing failed");
      render(await response.json());
    } catch {
      showError();
    }
  };

  openButton.addEventListener("click", () => {
    dialog.showModal();
    load();
  });
  closeButton.addEventListener("click", () => dialog.close());
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) dialog.close();
  });
  content.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-action]");
    if (!button) return;
    if (button.dataset.action === "select") {
      input.value = button.dataset.path;
      input.focus();
      dialog.close();
      return;
    }
    load(button.dataset.path);
  });
})();
