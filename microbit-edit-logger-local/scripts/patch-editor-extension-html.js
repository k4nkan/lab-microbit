const fs = require("fs");
const path = require("path");

const packageRoot = path.resolve(__dirname, "..");
const extensionRoot =
  process.env.EXT_DIR || path.resolve(packageRoot, "../microbit-edit-logger");
const source = path.join(extensionRoot, "editor", "extension.html");
const target = path.resolve(
  __dirname,
  "../node_modules/pxt-core/webapp/public/extension.html",
);
const backup = `${target}.original`;

if (!fs.existsSync(source)) {
  console.error(`Missing editor extension HTML: ${source}`);
  console.error("Set EXT_DIR to the microbit-edit-logger repository path.");
  process.exit(1);
}

if (!fs.existsSync(target)) {
  console.error(`Missing PXT extension HTML target: ${target}`);
  process.exit(1);
}

if (!fs.existsSync(backup)) {
  fs.copyFileSync(target, backup);
}

fs.copyFileSync(source, target);
console.log(`Patched PXT extension HTML: ${target}`);
