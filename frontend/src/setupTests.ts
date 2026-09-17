import '@testing-library/jest-dom'

// jsdom does not implement matchMedia, which Layout's useIsMobile calls on
// mount to pick the desktop or drawer rail.
window.matchMedia = window.matchMedia ?? (() => ({
  matches: false,
  media: '',
  onchange: null,
  addListener: () => {},
  removeListener: () => {},
  addEventListener: () => {},
  removeEventListener: () => {},
  dispatchEvent: () => false,
}))