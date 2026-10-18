"""Build a persistent QNN Vision worker using an existing SDK build, without editing it.

Run on the board with the organizer's completed ExecuTorch build. All generated
source, objects and binaries go under --output-dir (use /tmp for experiments).
"""

import argparse
import hashlib
import json
import re
import shlex
import subprocess
from pathlib import Path


def transform(source):
    """Keep the supplied loader/kernels; add a request loop after model loading."""
    if 'const bool persistent_stdin = (FLAGS_input_list_path == "-");' in source:
        # Some organizer checkouts already support a per-frame stdin loop. Normalize
        # its input dispatch in our generated copy, without touching that checkout.
        begin = source.index("  // Fill in data for input")
        split = source.index("    auto split =", begin)
        source = source[:begin] + '''  // Fill in data for input
  std::ifstream input_list(FLAGS_input_list_path);
  if (input_list.is_open()) {
    size_t num_inputs = method->inputs_size();
''' + source[split:]
        source, count = re.subn(r'\n      if \(persistent_stdin\) \{.*?\n      \}\n', '\n', source, flags=re.S)
        if count != 1:
            raise ValueError("Unsupported organizer stdin completion marker")
        source = source.replace('std::to_string(persistent_stdin ? 0 : inference_index)',
                                'std::to_string(inference_index)')
    start = "  // Fill in data for input\n"
    end = "  // Dump the etdump data"
    if source.count(start) != 1 or source.count(end) != 1:
        raise ValueError("Unsupported SDK runner source; inspect its input and etdump boundaries")
    if "FLAGS_vision_resident" in source:
        raise ValueError("Source is already patched")
    source = source.replace("#include <fstream>", '#include <fstream>\n#include <iostream>\n'
                            'DEFINE_bool(vision_resident, false, "Retain loaded Vision model between requests.");', 1)
    # ETDump otherwise accumulates per-request events for the entire worker lifetime.
    source, count = re.subn(r'(program->load_method\([^;]*?)&etdump_gen',
                            r'\1(FLAGS_vision_resident ? nullptr : &etdump_gen)', source, count=1)
    if count != 1:
        raise ValueError("Unsupported SDK load_method call; cannot disable accumulating traces")
    source = source.replace(start, '''  if (FLAGS_vision_resident) {
    ET_CHECK_MSG(!FLAGS_dump_intermediate_outputs, "Resident mode does not support debug dumps");
    std::cout << "VISION_READY" << std::endl;
  }
  do {
    if (FLAGS_vision_resident) {
      if (!std::getline(std::cin, FLAGS_input_list_path)) break;
      if (!std::getline(std::cin, FLAGS_output_folder_path)) break;
      ET_CHECK_MSG(!FLAGS_input_list_path.empty() && !FLAGS_output_folder_path.empty(),
                   "Resident request paths must not be empty");
    }
''' + start, 1)
    source = source.replace(end, '''    if (!FLAGS_vision_resident) break;
    std::cout << "VISION_DONE" << std::endl;
  } while (true);
''' + end, 1)
    return source


def build(sdk, build_dir, output):
    sdk, build_dir, output = map(lambda p: Path(p).resolve(), (sdk, build_dir, output))
    if output == sdk or sdk in output.parents:
        raise ValueError("Output must be outside the SDK checkout; use /tmp/vision-worker")
    source = sdk / "examples/qualcomm/executor_runner/qnn_executor_runner.cpp"
    target = build_dir / "examples/qualcomm/executor_runner/CMakeFiles/qnn_executor_runner.dir"
    original = source.read_text(encoding="utf-8")
    output.mkdir(parents=True, exist_ok=True)
    patched = output / "qnn_vision_worker.cpp"
    patched.write_text(transform(original), encoding="utf-8")
    cache = (build_dir / "CMakeCache.txt").read_text()
    home = re.search(r"^CMAKE_HOME_DIRECTORY:INTERNAL=(.+)$", cache, re.M)
    recorded_sdk = home[1] if home else str(sdk)
    if recorded_sdk.endswith("/examples/qualcomm"):
        recorded_sdk = recorded_sdk.removesuffix("/examples/qualcomm")

    def relocate(token):
        # Relative CMake object names may embed the historical source path; leave
        # them intact. Only absolute compiler/include/library paths are relocated.
        if token.startswith(("/", "-I/", "-L/", "-Wl,")):
            return token.replace(recorded_sdk, str(sdk))
        return token
    compiler = re.search(r"^CMAKE_CXX_COMPILER:(?:FILEPATH|STRING)=(.+)$", cache, re.M)
    if compiler is None:
        raise ValueError("SDK build has no recorded C++ compiler")
    flags = (target / "flags.make").read_text()
    options = []
    for key in ("CXX_DEFINES", "CXX_INCLUDES", "CXX_FLAGS"):
        match = re.search(rf"^{key} = (.*)$", flags, re.M)
        if match is None:
            raise ValueError(f"SDK build is missing {key}; use its Unix Makefiles build")
        options.extend(relocate(t) for t in shlex.split(match[1]))
    obj = output / "qnn_vision_worker.cpp.o"
    compile_command = [compiler[1], *options, "-c", str(patched), "-o", str(obj)]
    # Reuse the exact organizer build's ABI, linked kernels and QNN backend.
    link_command = [relocate(t) for t in shlex.split((target / "link.txt").read_text())]
    found_object = found_output = False
    for i, token in enumerate(link_command):
        if token.endswith("/qnn_executor_runner.cpp.o"):
            link_command[i] = str(obj)
            found_object = True
        if i > 0 and link_command[i - 1] == "-o":
            link_command[i] = str(output / "qnn_vision_worker")
            found_output = True
    if not found_object or not found_output:
        raise ValueError("Unsupported SDK link command; no original runner object/output")
    subprocess.run(compile_command, cwd=target.parent.parent, check=True)
    subprocess.run(link_command, cwd=target.parent.parent, check=True)
    manifest = {"sdk": str(sdk), "sdk_build": str(build_dir),
                "source_sha256": hashlib.sha256(original.encode()).hexdigest(),
                "worker_sha256": hashlib.sha256((output / "qnn_vision_worker").read_bytes()).hexdigest(),
                "compile_command": compile_command, "link_command": link_command}
    (output / "build.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(output / "qnn_vision_worker")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk", required=True)
    parser.add_argument("--build-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    build(args.sdk, args.build_dir, args.output_dir)
