declare const widget: { run(): void };
// @ts-expect-error legacy widget has no missing() until v3
widget.missing();
// widget internals are not typed
const x = widget.other;
