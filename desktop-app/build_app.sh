#!/bin/zsh
set -euo pipefail

ROOT="${0:A:h}"
cd "$ROOT"

export ELECTRON_CACHE="$ROOT/.electron-cache"
export electron_config_cache="$ROOT/.electron-cache"
export XDG_CACHE_HOME="$ROOT/.cache"
export npm_config_cache="$ROOT/.npm-cache"

npm install

ELECTRON_VERSION="$(node -p "require('./node_modules/electron/package.json').version")"
ZIP="$(find "$ROOT/.electron-cache" -name "electron-v${ELECTRON_VERSION}-darwin-arm64.zip" -type f | head -1)"
if [[ -z "$ZIP" ]]; then
  mkdir -p "$ROOT/.electron-cache/downloads"
  ZIP="$ROOT/.electron-cache/downloads/electron-v${ELECTRON_VERSION}-darwin-arm64.zip"
  curl -L --fail --output "$ZIP" \
    "https://github.com/electron/electron/releases/download/v${ELECTRON_VERSION}/electron-v${ELECTRON_VERSION}-darwin-arm64.zip"
fi

UNPACKED="$ROOT/.cache/electron-unpacked"
APP="$ROOT/dist/Open Knowledge Agent.app"

rm -rf "$UNPACKED" "$APP"
mkdir -p "$UNPACKED" "$ROOT/dist"
/usr/bin/ditto -x -k "$ZIP" "$UNPACKED"
/usr/bin/ditto "$UNPACKED/Electron.app" "$APP"

mv "$APP/Contents/MacOS/Electron" "$APP/Contents/MacOS/OpenKnowledgeAgent"

PLIST="$APP/Contents/Info.plist"

/usr/libexec/PlistBuddy -c "Set :CFBundleExecutable OpenKnowledgeAgent" "$PLIST"
/usr/libexec/PlistBuddy -c "Set :CFBundleDisplayName Open Knowledge Agent" "$PLIST"
/usr/libexec/PlistBuddy -c "Set :CFBundleName Open Knowledge Agent" "$PLIST"
/usr/libexec/PlistBuddy -c "Set :CFBundleIdentifier app.openknowledgeagent.desktop" "$PLIST"
/usr/libexec/PlistBuddy -c "Set :CFBundleIconFile AppIcon.icns" "$PLIST"
/usr/libexec/PlistBuddy -c "Delete :ElectronAsarIntegrity" "$PLIST" 2>/dev/null || true

/usr/libexec/PlistBuddy -c "Add :NSMicrophoneUsageDescription string Open Knowledge Agent uses the microphone for voice chat." "$PLIST" 2>/dev/null || \
  /usr/libexec/PlistBuddy -c "Set :NSMicrophoneUsageDescription Open Knowledge Agent uses the microphone for voice chat." "$PLIST"
/usr/libexec/PlistBuddy -c "Add :NSSpeechRecognitionUsageDescription string Open Knowledge Agent uses macOS speech recognition to turn your voice into a chat prompt." "$PLIST" 2>/dev/null || \
  /usr/libexec/PlistBuddy -c "Set :NSSpeechRecognitionUsageDescription Open Knowledge Agent uses macOS speech recognition to turn your voice into a chat prompt." "$PLIST"

rm -f "$APP/Contents/Resources/default_app.asar"
mkdir -p "$APP/Contents/Resources/app"
cp "$ROOT/package.json" "$APP/Contents/Resources/app/package.json"
cp "$ROOT/package-lock.json" "$APP/Contents/Resources/app/package-lock.json"
cp -R "$ROOT/src" "$APP/Contents/Resources/app/src"
cp -R "$ROOT/assets" "$APP/Contents/Resources/app/assets"
cp -R "$ROOT/vendor" "$APP/Contents/Resources/app/vendor"
mkdir -p "$APP/Contents/Resources/app/backend"
cp -R "$ROOT/../study-agent/src" "$APP/Contents/Resources/app/backend/src"
mkdir -p "$APP/Contents/Resources/app/native"
export CLANG_MODULE_CACHE_PATH="$ROOT/.cache/clang-module-cache"
VOICE_APP="$APP/Contents/Resources/app/native/Open Knowledge Agent Voice.app"
mkdir -p "$VOICE_APP/Contents/MacOS"
clang -fobjc-arc -fblocks -framework Foundation -framework Speech -framework AVFoundation \
  "$ROOT/native/SpeechHelper.m" -o "$VOICE_APP/Contents/MacOS/SpeechHelper"
clang -fobjc-arc -fblocks -framework Foundation -framework Vision \
  "$ROOT/native/ImageTextHelper.m" -o "$VOICE_APP/Contents/MacOS/ImageTextHelper"
/usr/bin/plutil -create xml1 "$VOICE_APP/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Add :CFBundleExecutable string SpeechHelper" "$VOICE_APP/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Add :CFBundleIdentifier string app.openknowledgeagent.voice" "$VOICE_APP/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Add :CFBundleName string Open Knowledge Agent Voice" "$VOICE_APP/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Add :CFBundleDisplayName string Open Knowledge Agent Voice" "$VOICE_APP/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Add :CFBundlePackageType string APPL" "$VOICE_APP/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Add :LSUIElement bool true" "$VOICE_APP/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Add :NSMicrophoneUsageDescription string Open Knowledge Agent Voice uses the microphone for voice chat." "$VOICE_APP/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Add :NSSpeechRecognitionUsageDescription string Open Knowledge Agent Voice uses macOS speech recognition to turn your voice into a chat prompt." "$VOICE_APP/Contents/Info.plist"
(
  cd "$APP/Contents/Resources/app"
  npm ci --omit=dev --ignore-scripts
)
cp "$ROOT/assets/AppIcon.icns" "$APP/Contents/Resources/AppIcon.icns"

codesign --force --deep --sign - "$APP" >/dev/null
echo "$APP"

