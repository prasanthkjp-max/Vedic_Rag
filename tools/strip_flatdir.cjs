// Remove the dead `flatDir { ... }` repository that Capacitor's CLI template
// re-adds to android/capacitor-cordova-android-plugins/build.gradle on every
// `cap sync` (Gradle warns: "Using flatDir should be avoided because it
// doesn't support any meta-data formats"). No Cordova plugins are installed
// and the directories it points at don't exist, so nothing resolves through
// it. Wired into the npm cap:* scripts; still present in Capacitor 8.4.1,
// so re-check before dropping this on a Capacitor upgrade.
const fs = require('fs');
const path = require('path');

const f = path.join(__dirname, '..', 'android',
    'capacitor-cordova-android-plugins', 'build.gradle');
if (fs.existsSync(f)) {
    const src = fs.readFileSync(f, 'utf8');
    const out = src.replace(/\n\s*flatDir\s*\{[^}]*\}/g, '');
    if (out !== src) {
        fs.writeFileSync(f, out);
        console.log('stripped flatDir from', path.relative(process.cwd(), f));
    }
}
