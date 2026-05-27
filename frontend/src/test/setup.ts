import "@testing-library/jest-dom/vitest";

Object.defineProperty(window, "matchMedia", {
	writable: true,
	value: (query: string) => ({
		matches: false,
		media: query,
		onchange: null,
		addListener: () => {},
		removeListener: () => {},
		addEventListener: () => {},
		removeEventListener: () => {},
		dispatchEvent: () => false,
	}),
});

class ResizeObserverMock {
	observe() {}

	unobserve() {}

	disconnect() {}
}

Object.defineProperty(window, "ResizeObserver", {
	writable: true,
	value: ResizeObserverMock,
});

Object.defineProperty(window, "visualViewport", {
	writable: true,
	value: {
		addEventListener: () => {},
		removeEventListener: () => {},
	},
});

Object.defineProperty(document, "fonts", {
	writable: true,
	value: {
		addEventListener: () => {},
		removeEventListener: () => {},
	},
});
