'use strict';

window.partialsReady = (async function loadPartials() {
  const includeNodes = Array.from(document.querySelectorAll('[data-include]'));

  if (!includeNodes.length) {
    document.dispatchEvent(new Event('partials:loaded'));
    return;
  }

  await Promise.all(
    includeNodes.map(async (node) => {
      const includePath = node.getAttribute('data-include');
      if (!includePath) return;

      try {
        const response = await fetch(includePath, { cache: 'no-cache' });
        if (!response.ok) {
          throw new Error(`Failed to load partial: ${includePath}`);
        }

        const html = await response.text();
        node.outerHTML = html;
      } catch (error) {
        node.innerHTML = '<p style="color:#ff6b6b;">Unable to load this section right now.</p>';
      }
    })
  );

  document.dispatchEvent(new Event('partials:loaded'));
})();
