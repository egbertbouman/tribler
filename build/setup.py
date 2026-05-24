from __future__ import annotations

import os
import platform
import re
import shutil
from pathlib import Path

from packaging.version import Version
from setuptools import find_packages

from win.build import setup, setup_executables, setup_options


def read_requirements(file_name: str, directory: str = ".") -> list[str]:
    """
    Read the pip requirements from the given file name in the given directory.
    """
    file_path = os.path.join(directory, file_name)
    if not os.path.exists(file_path):
        return []
    requirements = []
    with open(file_path, encoding="utf-8") as file:
        for line in file:
            # Check for a nested requirements file
            if line.startswith("-r"):
                nested_file = line.split(" ")[1].strip()
                requirements += read_requirements(nested_file, directory)
            elif not line.startswith("#") and line.strip() != "":
                requirements.append(line.strip().split("#")[0].strip())
    return requirements


base_dir = os.path.dirname(os.path.abspath(__file__))
install_requires = read_requirements("build/requirements.txt", base_dir)

build_mode = os.getenv("TRIBLER_BUILD_MODE", "regular")
if build_mode == "standalone":
    install_requires.extend(["PySide6>=6.0.0", "python-mpv>=1.0.0", "qasync"])

extras_require = {
    "dev": read_requirements("requirements-test.txt", base_dir),
}

# Copy src/run_tribler.py --> src/tribler/run.py to make it accessible in entry_points scripts.
# See: entry_points={"gui_scripts": ["tribler=tribler.run:main"]} in setup() below.
is_standalone = os.getenv("TRIBLER_BUILD_MODE") == "standalone"
build_opts = setup_options.setdefault("build_exe", {})
if is_standalone:
    with open("src/tribler/run.py", "w", encoding="utf-8") as f:
        f.write("import sys, os, asyncio, traceback\n")
        f.write("os.environ['QTWEBENGINE_DISABLE_GPU'] = '1'\n")
        f.write("print('[Standalone Wrapper] Starting startup sequence...', flush=True)\n")
        f.write("sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))\n")
        f.write("print('[Standalone Wrapper] Paths injected, importing run_tribler...', flush=True)\n")
        f.write("import run_tribler\n")
        f.write("print('[Standalone Wrapper] run_tribler imported successfully. Parsing arguments...', flush=True)\n")
        f.write("parsed_args = run_tribler.parse_args()\n")
        f.write("parsed_args['standalone'] = True\n")
        f.write("print(f'[Standalone Wrapper] Build mode enforced. Standalone: {parsed_args.get(\"standalone\")}', flush=True)\n")
        f.write("from PySide6.QtWidgets import QApplication\n")
        f.write("from qasync import QEventLoop\n")
        f.write("print('[Standalone Wrapper] Qt and QEventLoop loaded. Building event loop factory...', flush=True)\n")
        f.write("loop_factory = lambda: QEventLoop(QApplication.instance() or QApplication(sys.argv))\n")
        f.write("__restart = True\n")
        f.write("while __restart:\n")
        f.write("    print('[Standalone Wrapper] Launching asyncio event loop via asyncio.run()...', flush=True)\n")
        f.write("    try:\n")
        f.write("        __restart = asyncio.run(run_tribler.main(parsed_args), loop_factory=loop_factory)\n")
        f.write("    except Exception as e:\n")
        f.write("        print(f'[Standalone Wrapper] CRITICAL CRASH detected inside run_tribler.main: {e}', flush=True)\n")
        f.write("        traceback.print_exc(file=sys.stdout)\n")
        f.write("        sys.stdout.flush()\n")
        f.write("        __restart = False\n")
        f.write("    print(f'[Standalone Wrapper] Loop execution finished. Restart requested? {__restart}', flush=True)\n")
    
    build_opts.setdefault("packages", []).extend([
        "PySide6.QtWebEngineWidgets", 
        "PySide6.QtWebEngineCore", 
        "mpv", 
        "qasync",
        "tribler.ui"
    ])
    
    import PySide6
    pyside_dir = os.path.dirname(PySide6.__file__)
    for subfolder in ["QtWebEngineProcess", "translations", "resources"]:
        full_path = os.path.join(pyside_dir, subfolder)
        if os.path.exists(full_path):
            build_opts.setdefault("include_files", []).append((full_path, subfolder))
            
    for lib, name in [("src/mpv-1.dll", "mpv-1.dll"), ("src/libmpv.dylib", "libmpv.dylib"), ("src/libmpv.so", "libmpv.so")]:
        if os.path.exists(lib):
            build_opts.setdefault("include_files", []).append((lib, name))
            
    if platform.system() == "Windows":
        for exe in setup_executables: exe.base = "Win32GUI"
else:
    shutil.copy("src/run_tribler.py", "src/tribler/run.py")
    build_opts.setdefault("excludes", []).extend(["PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineCore", "mpv", "qasync"])

# Turn the tag into a sequence of integer values and normalize into a period-separated string.
raw_version = os.getenv("GITHUB_TAG", "0.0.0")
version_numbers = [str(value) for value in map(int, re.findall(r"\d+", raw_version))]
version = Version(".".join(version_numbers))

# cx_Freeze does not automatically make the package metadata
package_name = "tribler-standalone" if build_mode == "standalone" else "tribler"
for name in list({package_name, "tribler"}):
    os.makedirs(f"{name}.dist-info", exist_ok=True)
    with open(f"{name}.dist-info/METADATA", "w") as metadata_file:
        metadata_file.write(f"""Metadata-Version: 2.3
Name: {name.capitalize()}
Version: {str(version)}""")

setup(
    name=package_name,
    version=str(version),
    description=("Tribler" if platform.system() == "Windows"  # This is what you see in Task Manager
                 else "Privacy enhanced BitTorrent client with P2P content discovery"),
    long_description=Path("README.rst").read_text(encoding="utf-8"),
    long_description_content_type="text/x-rst",
    author="Tribler Team",
    author_email="info@tribler.org",
    url="https://github.com/Tribler/tribler",
    keywords="BitTorrent client, file sharing, peer-to-peer, P2P, TOR-like network",
    python_requires=">=3.8",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    include_package_data=True,
    install_requires=install_requires,
    extras_require=extras_require,
    entry_points={
        "gui_scripts": [
            "tribler=tribler.run:main",
        ]
    },
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "Intended Audience :: End Users/Desktop",
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.12",
        "Topic :: Communications :: File Sharing",
        "Topic :: Security :: Cryptography",
        "Operating System :: OS Independent",
    ],
    options=setup_options,
    executables=setup_executables
)
