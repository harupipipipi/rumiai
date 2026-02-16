/**
 * Router - SPAルーティング
 */

let routeHandlers = {};

export function registerRoute(pattern, handler) { routeHandlers[pattern] = handler; }

export function navigate(path, replace = false) {
  if (replace) history.replaceState(null, '', path);
  else history.pushState(null, '', path);
  handleRoute();
}

export function handleRoute() {
  const path = window.location.pathname;
  const chatMatch = path.match(/^\/chats\/([a-f0-9-]+)$/i);
  if (chatMatch) {
    if (routeHandlers['chat']) routeHandlers['chat'](chatMatch[1]);
    return;
  }
  if (path === '/' || path === '') {
    if (routeHandlers['home']) routeHandlers['home']();
    return;
  }
  if (routeHandlers['notFound']) routeHandlers['notFound']();
}

window.addEventListener('popstate', handleRoute);
