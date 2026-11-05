import base64, unittest
from src.collector import parse_vpngate_csv
from src.vps_openvpn_verify import sanitize_profile

class Tests(unittest.TestCase):
    def test_csv_profile_and_remote_port(self):
        profile = base64.b64encode(b"client\nremote vpn.example 443\nproto tcp\n").decode()
        raw = "*comment\nHostName,IP,Score,Ping,Speed,CountryLong,CountryShort,OpenVPN_ConfigData_Base64\nnode,203.0.113.4,10,20,3000,Example,EX," + profile + "\n"
        rows = parse_vpngate_csv(raw)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["host"], "203.0.113.4")
        self.assertEqual(rows[0]["port"], 443)

    def test_invalid_profile_skipped(self):
        raw = "HostName,IP,Score,Ping,Speed,CountryLong,CountryShort,OpenVPN_ConfigData_Base64\nnode,1.2.3.4,1,1,1,X,XX,bad!\n"
        self.assertEqual(parse_vpngate_csv(raw), [])

    def test_unsafe_directives_removed(self):
        safe = sanitize_profile("client\nscript-security 2\nup /tmp/a.sh\nredirect-gateway def1\nremote x 1194\n")
        self.assertIn("route-nopull", safe)
        self.assertIn("remote x 1194", safe)
        self.assertNotIn("script-security", safe)
        self.assertNotIn("redirect-gateway", safe)

if __name__ == "__main__":
    unittest.main()
