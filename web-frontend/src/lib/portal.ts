// Portal utility for rendering components at document body level
export function portal(node: HTMLElement) {
  const portal = document.createElement('div');
  portal.className = 'svelte-portal';
  portal.style.position = 'fixed';
  portal.style.zIndex = '99999';
  portal.style.top = '0';
  portal.style.left = '0';
  
  document.body.appendChild(portal);
  portal.appendChild(node);
  
  return {
    destroy() {
      if (portal.parentNode) {
        portal.parentNode.removeChild(portal);
      }
    }
  };
}