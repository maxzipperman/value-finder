"""Synthetic, standard-library-only example; never sends requests."""
import json


def describe(text):
    return len(json.loads(text))
