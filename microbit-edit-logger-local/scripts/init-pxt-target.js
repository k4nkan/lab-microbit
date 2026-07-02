const fs = require("fs");
const path = require("path");

const targetDirName = "pxt-microbit";
const packageRoot = process.cwd();
const nodeModulesDir = path.join(packageRoot, "node_modules");
const targetDir = path.join(nodeModulesDir, targetDirName);
const targetJson = path.join(targetDir, "pxtarget.json");
const cliConfig = path.join(nodeModulesDir, "pxtcli.json");

if (!fs.existsSync(targetJson)) {
  console.error(`Missing ${path.relative(packageRoot, targetJson)}.`);
  console.error("Run npm install first.");
  process.exit(1);
}

fs.writeFileSync(
  cliConfig,
  JSON.stringify({ targetdir: targetDirName }, null, 4) + "\n",
);
console.log(
  `Initialized ${path.relative(packageRoot, cliConfig)} for ${targetDirName}.`,
);
