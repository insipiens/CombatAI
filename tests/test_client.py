from __future__ import annotations

import json
import socket
import threading
import unittest

from combatai.dcs_client import DcsMenuClient


class ClientTests(unittest.TestCase):
    def test_retries_execute_with_same_request_id(self) -> None:
        server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        server.bind(("127.0.0.1", 0))
        server.settimeout(1.0)
        server_port = server.getsockname()[1]

        with DcsMenuClient(listen_port=0, dcs_port=server_port) as client:
            client_address = client._socket.getsockname()  # Test the real UDP boundary.
            received_ids: list[str] = []

            def dcs_stub() -> None:
                try:
                    first, _ = server.recvfrom(65535)
                    received_ids.append(json.loads(first)["request_id"])
                    second, _ = server.recvfrom(65535)
                    request_id = json.loads(second)["request_id"]
                    received_ids.append(request_id)
                    reply = json.dumps(
                        {
                            "v": 1,
                            "type": "result",
                            "request_id": request_id,
                            "accepted": True,
                            "code": "accepted",
                            "detail": "",
                        },
                        separators=(",", ":"),
                    ).encode()
                    server.sendto(reply, client_address)
                finally:
                    server.close()

            worker = threading.Thread(target=dcs_stub, daemon=True)
            worker.start()
            request_id = client.execute("f10.1", revision=3)
            result = client.wait_for_result(request_id, timeout=0.5, retry_interval=0.05)
            worker.join(timeout=1.0)

        self.assertIsNotNone(result)
        assert result is not None
        self.assertTrue(result.accepted)
        self.assertEqual(received_ids, [request_id, request_id])


if __name__ == "__main__":
    unittest.main()
