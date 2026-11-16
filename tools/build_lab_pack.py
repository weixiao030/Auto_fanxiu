"""Make an isolated pack to parse the bridge without starting any game/login code."""
import hashlib
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parent.parent


def write_pack(path, files):
    entries = []
    directory_size = 100
    for name, content in files.items():
        encoded = name.encode('utf-8')
        encoded += b'\0' * ((-len(encoded)) % 4)
        entries.append([encoded, content, 0])
        directory_size += 40 + len(encoded)
    position = (directory_size + 15) // 16 * 16
    for entry in entries:
        entry[2] = position
        position += len(entry[1])
        position = (position + 15) // 16 * 16
    with path.open('wb') as out:
        out.write(struct.pack('<4s5IQ', b'GDPC', 2, 4, 7, 1, 0, 0) + bytes(64))
        out.write(struct.pack('<I', len(entries)))
        for name, content, offset in entries:
            out.write(struct.pack('<I', len(name)) + name + struct.pack('<QQ', offset, len(content))
                      + hashlib.md5(content).digest() + struct.pack('<I', 0))
        for _, content, offset in entries:
            out.write(bytes(offset - out.tell()))
            out.write(content)


if __name__ == '__main__':
    output = ROOT / '.private/bridge-lab.pck'
    output.parent.mkdir(exist_ok=True)
    write_pack(output, {
        'res://project.godot': b'config_version=5\n[application]\nconfig/name="AssistantSyntaxLab"\nrun/main_scene="res://main.tscn"\n[rendering]\nrenderer/rendering_method="gl_compatibility"\n',
        'res://main.tscn': b'[gd_scene load_steps=2 format=3]\n[ext_resource type="Script" path="res://assistant.gd" id="1"]\n[node name="AssistantSyntaxLab" type="Node"]\nscript = ExtResource("1")\n',
        'res://assistant.gd': (ROOT / 'bridge/assistant.gd').read_bytes(),
    })
    print(output)
