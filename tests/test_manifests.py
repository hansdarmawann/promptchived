from promptchived.importers.manifests import read_manifest


def test_manifest_accepts_windows_1252(tmp_path):
    path = tmp_path / "1.txt"
    path.write_bytes("C:\\Exports\\café\\MyActivity.html\r\n".encode("cp1252"))
    entries = read_manifest(path)
    assert len(entries) == 1
    assert "café" in str(entries[0])
