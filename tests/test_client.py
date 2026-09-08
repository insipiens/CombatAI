from __future__ import annotations

import json
import socket
import threading
import unittest

from combatai.dcs_client import DcsMenuClient


class ClientTests(unittest.TestCase):
    def test_windows_udp_reset_is_treated_as_no_message(self) -> None:
        class ResetSocket:
            def recvfrom(self, _size: int) -> tuple[bytes, tuple[str, int]]:
                raise ConnectionResetError(10054, "forcibly closed by remote host")

            def close(self) -> None:
                pass

        client = DcsMenuClient(listen_port=0)
        real_socket = client._socket
        client._socket = ResetSocket()  # type: ignore[assignment]
        real_socket.close()
        try:
            self.assertIsNone(client.receive_once())
        finally:
            client.close()

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

    def test_open_menu_sends_a_revision_checked_non_executable_request(self) -> None:
        server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        server.bind(("127.0.0.1", 0))
        server.settimeout(1.0)
        server_port = server.getsockname()[1]
        try:
            with DcsMenuClient(listen_port=0, dcs_port=server_port) as client:
                request_id = client.open_menu("menu.5.1", revision=7)
                payload, _ = server.recvfrom(65535)
                message = json.loads(payload)
        finally:
            server.close()

        self.assertEqual(message["type"], "open_menu")
        self.assertEqual(message["request_id"], request_id)
        self.assertEqual(message["menu_id"], "menu.5.1")
        self.assertEqual(message["revision"], 7)
        self.assertNotIn("action_id", message)


if __name__ == "__main__":
    unittest.main()
