import json
import unittest

from blanco_pairing_poc import PacketAssembler, PairingError, extract_dev_id, make_token


class ProtocolTests(unittest.TestCase):
    def test_token_is_deterministic(self):
        self.assertEqual(
            make_token("12345", 1234567, 9876543),
            "729e9a91e0162e42d3125a10e3b6e0addcdb28b1dc1ec7ecaa52c247cae9f111",
        )

    def test_reassembles_fragmented_response(self):
        response = {
            "body": {"meta": {"dev_id": "a" * 64, "dev_type": 1}}
        }
        encoded = json.dumps(response, separators=(",", ":")).encode() + b"\x00\xff"
        first = bytes((0xFF, 0, 2, 7, 0)) + encoded[: len(encoded) // 2]
        second = bytes((7, 1)) + encoded[len(encoded) // 2 :]
        assembler = PacketAssembler()
        self.assertIsNone(assembler.add(first))
        self.assertEqual(assembler.add(second), response)

    def test_rejects_bad_header(self):
        with self.assertRaises(PairingError):
            PacketAssembler().add(b"\xff\x01\x01\x01\x00{}")

    def test_validates_dev_id(self):
        self.assertEqual(extract_dev_id({"body": {"meta": {"dev_id": "b" * 64}}})[0], "b" * 64)
        with self.assertRaises(PairingError):
            extract_dev_id({"body": {"meta": {"dev_id": "not-an-id"}}})


if __name__ == "__main__":
    unittest.main()
