class AppTestBZ2File:
    spaceconfig = {
        "usemodules": ["_lzma"]
    }

    def test_module(self):
        import lzma

    def test_simple_compress(self):
        import lzma
        compressed = lzma.compress(b'Insert Data Here', format=lzma.FORMAT_ALONE)
        assert compressed == (b']\x00\x00\x80\x00\xff\xff\xff\xff\xff'
                              b'\xff\xff\xff\x00$\x9b\x8afg\x91'
                              b'(\xcb\xde\xfa\x03\r\x1eQT\xbe'
                              b't\x9e\xdfI]\xff\xf4\x9d\x80\x00')
        decompressed = lzma.decompress(compressed)
        assert decompressed == b'Insert Data Here'
