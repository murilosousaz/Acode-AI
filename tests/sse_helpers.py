import json


def parse_events(body: str):
    """Lê o corpo SSE como o navegador: ignora comentários (":") e devolve [(evento, dados)]."""
    events = []
    for block in body.split("\n\n"):
        name, data = None, None
        for line in block.splitlines():
            if line.startswith("event: "):
                name = line[len("event: "):]
            elif line.startswith("data: "):
                data = json.loads(line[len("data: "):])
        if name:
            events.append((name, data))
    return events
