"""Configuration and toolchain locator for APK to Android TV Converter.
"""
from pathlib import Path
import os
import shutil

BASE_DIR = Path(__file__).resolve().parent
TOOLS_DIR = BASE_DIR / "tools"

def find_android_sdk_tool(tool_name: str) -> Path | None:
    """Search for tool in ANDROID_HOME, ANDROID_SDK_ROOT, or common default paths."""
    candidates = []
    for env_var in ("ANDROID_HOME", "ANDROID_SDK_ROOT", "LOCALAPPDATA"):
        val = os.environ.get(env_var)
        if val:
            p = Path(val)
            if env_var == "LOCALAPPDATA":
                candidates.append(p / "Android" / "Sdk")
            else:
                candidates.append(p)
    
    # Common windows default
    candidates.append(Path.home() / "AppData" / "Local" / "Android" / "Sdk")
    
    for sdk_path in candidates:
        if not sdk_path.exists():
            continue
        build_tools_dir = sdk_path / "build-tools"
        if build_tools_dir.exists():
            # Pick newest version
            versions = sorted(build_tools_dir.iterdir(), key=lambda x: x.name, reverse=True)
            for v in versions:
                target = v / tool_name
                if target.exists():
                    return target
                target_exe = v / f"{tool_name}.exe"
                if target_exe.exists():
                    return target_exe
                target_bat = v / f"{tool_name}.bat"
                if target_bat.exists():
                    return target_bat
    
    # Also check system PATH
    which_path = shutil.which(tool_name)
    if which_path:
        return Path(which_path)
    return None

JAVA_CMD = shutil.which("java") or "java"
APKTOOL_JAR = TOOLS_DIR / "apktool.jar"

def ensure_apktool() -> Path:
    """Ensure apktool.jar is present, downloading if necessary."""
    if not APKTOOL_JAR.exists():
        TOOLS_DIR.mkdir(parents=True, exist_ok=True)
        url = "https://bitbucket.org/iBotPeaches/apktool/downloads/apktool_2.10.0.jar"
        import urllib.request
        print(f"Downloading apktool.jar to {APKTOOL_JAR}...")
        urllib.request.urlretrieve(url, APKTOOL_JAR)
    return APKTOOL_JAR

ZIPALIGN_EXE = find_android_sdk_tool("zipalign")
APKSIGNER_CMD = find_android_sdk_tool("apksigner")
AAPT2_EXE = find_android_sdk_tool("aapt2")

DEFAULT_KEYSTORE = Path.home() / ".android" / "debug.keystore"
KEYSTORE_PASS = "android"
KEY_ALIAS = "androiddebugkey"
KEY_PASS = "android"

# Known manifest attributes introduced post-API 30 that cause AAPT2 link failures
# when targeting TV baseline (Android 11 / API 30). Centralized for maintainability.
UNSUPPORTED_POST_API30_ATTRS = [
    # Android 12 (API 31/32)
    "splashScreenTheme",
    "windowSplashScreenAnimatedIcon",
    "windowSplashScreenAnimationDuration",
    "windowSplashScreenBackground",
    "windowSplashScreenIconBackgroundColor",
    "windowSplashScreenBrandingImage",
    "attributionsAreUserVisible",
    # Android 13 (API 33)
    "enableOnBackInvokedCallback",
    "localeConfig",
    "canDisplayOnRemoteDevices",
    # Android 14 (API 34)
    "knownActivityEmbeddingCerts",
    "requiredDisplayCategory",
    # Android 15 & 16 (API 35/36)
    "allowCrossUidActivitySwitchFromBelow",
    "cloudMediaProviderAuthority",
    "allowUndo",
    "overrideOrientation",
    "preserveWindowPosition",
    "enableDesktopModeOnSecondaryDisplays",
]

# TV Profile Constraints
TARGET_SCREEN_WIDTH = 1280
TARGET_SCREEN_HEIGHT = 720
TARGET_BANNER_WIDTH = 320
TARGET_BANNER_HEIGHT = 180
MAX_HEAP_MB = 192
API_LEVEL = 30
