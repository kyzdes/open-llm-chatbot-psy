import html


def weekly_summary(entries: list[dict]) -> str:
    if not entries:
        return "За последнюю неделю нет записей настроения. Используй /mood чтобы начать."

    scores = [e["score"] for e in entries]
    avg = sum(scores) / len(scores)
    trend = _compute_trend(scores)

    lines = [f"📓 <b>Дневник настроения за неделю</b> ({len(entries)} записей)\n"]
    lines.append(f"Средняя оценка: <b>{avg:.1f}</b> / 10")
    lines.append(f"Тренд: {trend}\n")

    for e in entries:
        date = e["created_at"][:16].replace("T", " ") if e["created_at"] else "?"
        bar = _score_bar(e["score"])
        note_part = f' — <i>{html.escape(e["note"])}</i>' if e.get("note") else ""
        lines.append(f"<code>{date}</code> {bar} {e['score']}/10{note_part}")

    return "\n".join(lines)


def _compute_trend(scores: list[int]) -> str:
    if len(scores) < 2:
        return "недостаточно данных"
    first_half = scores[: len(scores) // 2]
    second_half = scores[len(scores) // 2 :]
    avg1 = sum(first_half) / len(first_half)
    avg2 = sum(second_half) / len(second_half)
    diff = avg2 - avg1
    if diff > 0.5:
        return "📈 улучшение"
    elif diff < -0.5:
        return "📉 снижение"
    return "➡️ стабильно"


def _score_bar(score: int) -> str:
    filled = "█" * score
    empty = "░" * (10 - score)
    return f"[{filled}{empty}]"
