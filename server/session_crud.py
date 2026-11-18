

import json
import time

import server.msg_store as _msgst



_TABLES = {
    "main": ("sessions", "currentId"),
    "agent": ("agent_sessions", "agentCurrentId"),
}


_PREFIX_KIND = {"s_": "main", "ag_": "agent"}


def kind_of(sid):
    
    for pre, k in _PREFIX_KIND.items():
        if isinstance(sid, str) and sid.startswith(pre):
            return k
    return "main"


def _tables(kind):
    if kind not in _TABLES:
        raise ValueError("unknown kind: %r" % (kind,))
    return _TABLES[kind]


def _load_doc(conn, kind, sid):
    
    table, _ = _tables(kind)
    row = conn.execute("SELECT data FROM %s WHERE id=?" % table, (sid,)).fetchone()
    if not row:
        return None
    try:
        obj = json.loads(row[0])
    except (TypeError, ValueError):
        return None
    return obj if isinstance(obj, dict) else None


def _write_doc(conn, kind, sid, doc):
    table, _ = _tables(kind)
    conn.execute("UPDATE %s SET data=?, name=? WHERE id=?" % table,
                 (json.dumps(doc, ensure_ascii=False), doc.get("name") or "未命名会话", sid))


def _set_current(conn, kind, sid):
    _, curkey = _tables(kind)
    conn.execute(
        "INSERT INTO meta(key, value) VALUES(?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (curkey, sid))






def create_session(conn, kind, sid, name=None, set_current=True):
    
    table, _ = _tables(kind)
    exists = conn.execute("SELECT 1 FROM %s WHERE id=?" % table, (sid,)).fetchone()
    if exists:
        return False, None
    now = time.time()
    doc = {"id": sid, "name": (name or "").strip() or "未命名会话",
           "createdAt": now, "messages": []}
    conn.execute("INSERT INTO %s(id, name, created_at, data) VALUES(?,?,?,?)" % table,
                 (sid, doc["name"], now, json.dumps(doc, ensure_ascii=False)))
    if set_current:
        _set_current(conn, kind, sid)
    return True, doc


def rename_session(conn, kind, sid, name):
    
    doc = _load_doc(conn, kind, sid)
    if doc is None:
        return False
    doc["name"] = (name or "").strip() or "未命名会话"
    _write_doc(conn, kind, sid, doc)
    return True


def set_current_session(conn, kind, sid):
    
    table, _ = _tables(kind)
    if not conn.execute("SELECT 1 FROM %s WHERE id=?" % table, (sid,)).fetchone():
        return False
    _set_current(conn, kind, sid)
    return True






def append_messages(conn, kind, sid, messages):
    
    doc = _load_doc(conn, kind, sid)
    if doc is None:
        return None
    clean, _dropped, _big = _msgst.sanitize_messages(messages or [])
    msgs = doc.get("messages")
    if not isinstance(msgs, list):
        msgs = []
    msgs.extend(clean)
    doc["messages"] = msgs
    _write_doc(conn, kind, sid, doc)
    return len(clean)


def _match_message(msg, anchor):
    
    if not anchor:
        return True
    for k, v in anchor.items():
        if msg.get(k) != v:
            return False
    return True


def patch_message(conn, kind, sid, index, patch, anchor=None):
    
    doc = _load_doc(conn, kind, sid)
    if doc is None:
        return False
    msgs = doc.get("messages")
    if not isinstance(msgs, list) or not isinstance(index, int) or index < 0 or index >= len(msgs):
        return False
    msg = msgs[index]
    if not isinstance(msg, dict) or not _match_message(msg, anchor):
        return False
    clean, _, _ = _msgst.sanitize_messages([dict(msg, **(patch or {}))])
    if not clean:
        return False
    msgs[index] = clean[0]
    doc["messages"] = msgs
    _write_doc(conn, kind, sid, doc)
    return True


def delete_messages(conn, kind, sid, indices, anchors=None):
    
    doc = _load_doc(conn, kind, sid)
    if doc is None:
        return None
    msgs = doc.get("messages")
    if not isinstance(msgs, list) or not indices:
        return 0
    idxs = sorted({int(i) for i in indices if isinstance(i, int) and 0 <= int(i) < len(msgs)})
    drop = []
    for pos, idx in enumerate(idxs):
        anchor = (anchors[pos] if isinstance(anchors, list) and pos < len(anchors) else None)
        if _match_message(msgs[idx], anchor):
            drop.append(idx)
    for idx in reversed(drop):
        del msgs[idx]
    doc["messages"] = msgs
    _write_doc(conn, kind, sid, doc)
    return len(drop)


def replace_message(conn, kind, sid, index, msg, anchor=None):
    
    doc = _load_doc(conn, kind, sid)
    if doc is None:
        return False
    msgs = doc.get("messages")
    if not isinstance(msgs, list) or not isinstance(index, int) or index < 0 or index >= len(msgs):
        return False
    if not _match_message(msgs[index], anchor):
        return False
    clean, _, _ = _msgst.sanitize_messages([msg])
    if not clean:
        return False
    msgs[index] = clean[0]
    doc["messages"] = msgs
    _write_doc(conn, kind, sid, doc)
    return True








def _key_positions(msgs, key):
    
    out = []
    for i, m in enumerate(msgs):
        if isinstance(m, dict) and key in _msgst.msg_keys(m):
            out.append(i)
    return out


def upsert_message_by_key(conn, kind, sid, msg):
    
    doc = _load_doc(conn, kind, sid)
    if doc is None:
        return None
    clean, _, _ = _msgst.sanitize_messages([msg])
    if not clean:
        return (None, -1)
    msg = clean[0]
    msgs = doc.get("messages")
    if not isinstance(msgs, list):
        msgs = []
    pos = _key_positions(msgs, _msgst.msg_key(msg))
    if not pos:

        for k in _msgst.msg_keys(msg):
            pos = _key_positions(msgs, k)
            if pos:
                break
    if pos:
        idx = pos[0]
        msgs[idx] = _msgst.merge_msg(msgs[idx], msg)
        doc["messages"] = msgs
        _write_doc(conn, kind, sid, doc)
        return ("merged", idx)
    msgs.append(msg)
    doc["messages"] = msgs
    _write_doc(conn, kind, sid, doc)
    return ("added", len(msgs) - 1)


def delete_message_by_key(conn, kind, sid, key):
    
    doc = _load_doc(conn, kind, sid)
    if doc is None:
        return None
    msgs = doc.get("messages")
    if not isinstance(msgs, list):
        return 0
    pos = _key_positions(msgs, key)
    for idx in reversed(pos):
        del msgs[idx]
    if pos:
        doc["messages"] = msgs
        _write_doc(conn, kind, sid, doc)
    return len(pos)


def find_message_index(conn, kind, sid, key):
    
    doc = _load_doc(conn, kind, sid)
    if doc is None:
        return None
    msgs = doc.get("messages")
    if not isinstance(msgs, list):
        return -1
    pos = _key_positions(msgs, key)
    return pos[0] if pos else -1


def sync_messages(conn, kind, sid, messages):
    
    doc = _load_doc(conn, kind, sid)
    if doc is None:
        return None
    clean, _, _ = _msgst.sanitize_messages(messages or [])
    msgs = doc.get("messages")
    if not isinstance(msgs, list):
        msgs = []
    added = merged = 0
    for msg in clean:
        pos = _key_positions(msgs, _msgst.msg_key(msg))
        if not pos:
            for k in _msgst.msg_keys(msg):
                pos = _key_positions(msgs, k)
                if pos:
                    break
        if pos:
            msgs[pos[0]] = _msgst.merge_msg(msgs[pos[0]], msg)
            merged += 1
        else:
            msgs.append(msg)
            added += 1
    doc["messages"] = msgs
    _write_doc(conn, kind, sid, doc)
    return {"added": added, "merged": merged}
