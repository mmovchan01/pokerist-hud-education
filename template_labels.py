"""Portable folder names; '.' is a directory marker, never a valid folder label."""

def label_folder(label):
    return {'.': 'dot', ',': 'comma'}.get(label, label)


def folder_label(folder):
    return {'dot': '.', 'comma': ','}.get(folder, folder)
