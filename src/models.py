"""Shared data models."""

from dataclasses import dataclass


@dataclass
class Listing:
    id: str
    portal: str
    title: str
    price: str
    url: str
