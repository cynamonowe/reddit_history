#!/usr/bin/env python3
"""Merge the Arctic Shift dumps into one self-contained static HTML archive."""
import json, html, datetime, pathlib, collections

HERE = pathlib.Path(__file__).parent
USER = "WillyDreamwold"


def load(name):
    rows = []
    with open(HERE / name) as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def dedupe(rows):
    seen = {}
    for r in rows:
        seen[r["id"]] = r
    return list(seen.values())


comments = dedupe(load("comments_raw.jsonl"))
posts = dedupe(load("posts_raw.jsonl"))
ctx_posts = {p["id"]: p for p in load("context_posts.jsonl")}
ctx_comments = {c["id"]: c for c in load("context_parent_comments.jsonl")}

MISSING = "—"  # body genuinely absent from the archive


def txt(v):
    """Normalise a body/selftext field; None and '' both mean 'nothing here'."""
    if not v:
        return ""
    return v.replace("\r\n", "\n").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")


def trim_post(p):
    """The subset of a submission the page actually renders."""
    body = txt(p.get("selftext"))
    return {
        "id": p["id"],
        "t": p.get("title", ""),
        "s": p.get("subreddit", ""),
        "a": p.get("author", ""),
        "c": p.get("created_utc"),
        "sc": p.get("score"),
        "nc": p.get("num_comments"),
        "p": p.get("permalink", ""),
        "b": body,
        # url only matters when it points somewhere other than the post itself
        "u": "" if p.get("is_self") else (p.get("url") or ""),
        "dom": p.get("domain", ""),
        "f": p.get("link_flair_text") or "",
        "nsfw": bool(p.get("over_18")),
        # the archive captured some of these only after deletion
        "gone": body in ("[deleted]", "[removed]"),
    }


def trim_parent(c):
    body = txt(c.get("body"))
    return {
        "id": c["id"],
        "a": c.get("author", ""),
        "c": c.get("created_utc"),
        "sc": c.get("score"),
        "b": body,
        "p": c.get("permalink", ""),
        "gone": body in ("[deleted]", "[removed]"),
    }


# ---- comments, each stitched to its submission and its immediate parent ----
out_comments = []
missing_parents = []
for c in comments:
    link_id = (c.get("link_id") or "")[3:]
    parent_full = c.get("parent_id") or ""
    entry = {
        "k": "c",
        "id": c["id"],
        "s": c.get("subreddit", ""),
        "c": c.get("created_utc"),
        "sc": c.get("score"),
        "b": txt(c.get("body")),
        "p": c.get("permalink", ""),
        "op": bool(c.get("is_submitter")),
        "link": link_id,
        "top": parent_full.startswith("t3_"),
    }
    if parent_full.startswith("t1_"):
        pid = parent_full[3:]
        if pid in ctx_comments:
            entry["par"] = trim_parent(ctx_comments[pid])
        else:
            entry["par"] = None
            entry["parMissing"] = pid
            missing_parents.append((c["id"], pid))
    out_comments.append(entry)

out_posts = [dict(trim_post(p), k="p") for p in posts]

# Context submissions: the ones a comment hangs under. The user's own posts are
# already in out_posts, but a comment may point at either, so keep one table.
ctx = {pid: trim_post(p) for pid, p in ctx_posts.items()}

items = out_posts + out_comments
items.sort(key=lambda r: r["c"], reverse=True)

# ---- monthly activity buckets ----
buckets = collections.defaultdict(lambda: [0, 0])  # month -> [comments, posts]
for r in items:
    m = datetime.datetime.fromtimestamp(r["c"], datetime.timezone.utc).strftime("%Y-%m")
    buckets[m][0 if r["k"] == "c" else 1] += 1

first_m = min(buckets)
last_m = max(buckets)
y, mo = (int(x) for x in first_m.split("-"))
ey, emo = (int(x) for x in last_m.split("-"))
months = []
while (y, mo) <= (ey, emo):
    key = f"{y:04d}-{mo:02d}"
    months.append({"m": key, "c": buckets[key][0], "p": buckets[key][1]})
    mo += 1
    if mo == 13:
        y, mo = y + 1, 1

subs = collections.Counter(r["s"] for r in items)

data = {
    "user": USER,
    "userId": next((c.get("author_fullname") for c in comments if c.get("author_fullname")), ""),
    "generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d"),
    "items": items,
    "ctx": ctx,
    "months": months,
    "subs": subs.most_common(),
    "stats": {
        "comments": len(out_comments),
        "posts": len(out_posts),
        "subs": len(subs),
        "commentKarma": sum(r["sc"] or 0 for r in out_comments),
        "postKarma": sum(r["sc"] or 0 for r in out_posts),
        "first": min(r["c"] for r in items),
        "last": max(r["c"] for r in items),
        "missingParents": len(missing_parents),
        "goneBodies": sum(1 for r in out_posts if r["gone"]),
    },
}

payload = json.dumps(data, separators=(",", ":"), ensure_ascii=False).replace("</", "<\\/")

TEMPLATE = (HERE / "template.html").read_text()
out = TEMPLATE.replace("/*__DATA__*/null", payload)
(HERE / "index.html").write_text(out)

print(f"items: {len(items)}  (posts {len(out_posts)}, comments {len(out_comments)})")
print(f"context posts: {len(ctx)}   parent comments: {len(ctx_comments)}")
print(f"unresolved parents: {missing_parents}")
print(f"posts whose body was archived only post-deletion: {data['stats']['goneBodies']}")
print(f"wrote index.html ({(HERE / 'index.html').stat().st_size / 1024:.0f} KB)")
