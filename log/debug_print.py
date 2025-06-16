def print_object(obj, title=None, indent_level=1, visited=None):
    if title:
        print(title)

    if visited is None:
        visited = set()

    indent = '\t' * indent_level

    if id(obj) in visited:
        return
    visited.add(id(obj))

    for attr in dir(obj):
        if attr.startswith('_'):
            continue  # skip private/internal
        try:
            value = getattr(obj, attr)
        except Exception:
            continue  # skip inaccessible properties

        if callable(value):
            continue  # skip methods/functions

        print(f"{indent}{attr}:", end=' ')
        if hasattr(value, '__dict__') and not isinstance(value, (str, int, float, bool, list, dict, tuple, set)):
            print()
            print_object(value, indent_level=indent_level+1, visited=visited)
        else:
            print(value)
