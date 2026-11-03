"""Small bounded OpenSSH and netfilter adapters. Original messages are discarded."""

import re
from typing import Any

_AUTH = re.compile(
    r"^(?P<verb>Accepted|Failed) (?:password|publickey|keyboard-interactive/pam) for "
    r"(?:(?P<invalid>invalid user) )?(?P<username>\S{1,128}) from "
    r"(?P<src_ip>[0-9a-fA-F:.]{2,45}) port (?P<src_port>[0-9]{1,5})(?: |$)"
)
_INVALID = re.compile(
    r"^Invalid user (?P<username>\S{1,128}) from "
    r"(?P<src_ip>[0-9a-fA-F:.]{2,45})(?: port (?P<src_port>[0-9]{1,5}))?"
)
_DISCONNECT = re.compile(
    r"^(?:Disconnected from|Connection closed by|Received disconnect from) "
    r"(?:(?:authenticating user|invalid user|user) \S{1,128} )?"
    r"(?P<src_ip>[0-9a-fA-F:.]{2,45})(?:(?: port |:)(?P<src_port>[0-9]{1,5}))?"
)


def parse_journal(kind: str, timestamp: object, message: object) -> dict[str, Any]:
    if not isinstance(message, str) or len(message.encode("utf-8")) > 8192:
        raise ValueError("Invalid journal message")
    result: dict[str, Any] = {"timestamp": timestamp}
    if kind == "ssh":
        for pattern, outcome in (
            (_AUTH, "failure"),
            (_INVALID, "invalid_user"),
            (_DISCONNECT, "disconnect"),
        ):
            match = pattern.match(message)
            if match:
                fields = {key: value for key, value in match.groupdict().items() if value}
                verb = fields.pop("verb", None)
                invalid = fields.pop("invalid", None)
                result.update(
                    fields,
                    outcome=(
                        "success" if verb == "Accepted" else "invalid_user" if invalid else outcome
                    ),
                )
                if "src_port" in result:
                    result["src_port"] = int(result["src_port"])
                return result
        raise ValueError("Unsupported SSH message")
    if kind != "firewall":
        raise ValueError("Journal adapter only supports SSH/firewall")
    fields = dict(pair.split("=", 1) for pair in message.split() if "=" in pair)
    if "SRC" not in fields or "PROTO" not in fields:
        raise ValueError("Unsupported firewall message")
    for key, target in (("SRC", "src_ip"), ("DST", "dst_ip"), ("IN", "interface")):
        if fields.get(key):
            result[target] = fields[key]
    for key, target in (("SPT", "src_port"), ("DPT", "dst_port")):
        if key in fields:
            result[target] = int(fields[key])
    protocol = fields["PROTO"].lower()
    result["protocol"] = {"ipv6-icmp": "icmpv6", "icmpv6": "icmpv6"}.get(protocol, protocol)
    # A LOG statement alone does not establish a verdict.
    for marker, action in (
        ("AS_DROP:", "drop"),
        ("AS_ACCEPT:", "accept"),
        ("AS_REJECT:", "reject"),
    ):
        if message.startswith(marker):
            result["action"] = action
    return result


def adapt_journal(raw: object) -> object:
    if not isinstance(raw, dict):
        return raw
    payload = raw.get("payload")
    if not isinstance(payload, dict) or "journal_message" not in payload:
        return raw
    return {
        **raw,
        "payload": parse_journal(
            str(raw.get("source")), payload.get("timestamp"), payload["journal_message"]
        ),
    }
