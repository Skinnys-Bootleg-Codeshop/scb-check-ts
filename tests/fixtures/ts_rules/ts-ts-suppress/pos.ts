declare const widget: { run(): void };
// @ts-ignore
widget.missing(); // HIT
// @ts-nocheck
const x = widget.other; // HIT
// @ts-ignore
import { thing } from "./thing"; // HIT
