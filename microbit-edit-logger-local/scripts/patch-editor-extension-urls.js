const fs = require("fs");
const path = require("path");

const packageRoot = process.cwd();
const targetConfigPath = path.join(
  packageRoot,
  "node_modules",
  "pxt-microbit",
  "targetconfig.json",
);
const allowedUrls = [
  "http://localhost:8080/",
  "http://localhost:8080/extension.html",
  "http://127.0.0.1:8080/",
  "http://127.0.0.1:8080/extension.html",
  "http://[::1]:8080/",
  "http://[::1]:8080/extension.html",
];

if (!fs.existsSync(targetConfigPath)) {
  console.error(`Missing ${path.relative(packageRoot, targetConfigPath)}.`);
  console.error("Run npm install first.");
  process.exit(1);
}

const targetConfig = JSON.parse(fs.readFileSync(targetConfigPath, "utf8"));
targetConfig.packages = targetConfig.packages || {};
targetConfig.packages.approvedEditorExtensionUrls =
  targetConfig.packages.approvedEditorExtensionUrls || [];

let changed = false;
for (const url of allowedUrls) {
  if (!targetConfig.packages.approvedEditorExtensionUrls.includes(url)) {
    targetConfig.packages.approvedEditorExtensionUrls.push(url);
    changed = true;
  }
}

if (changed) {
  fs.writeFileSync(
    targetConfigPath,
    JSON.stringify(targetConfig, null, 4) + "\n",
  );
  console.log("Patched approved editor extension URLs for local development.");
} else {
  console.log("Local editor extension URLs are already approved.");
}
