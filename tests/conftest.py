"""Shared fixtures: a small in-memory database for tests."""

import sqlite3

import pytest

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import database as db


@pytest.fixture()
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    db.init_schema(c)
    c.executescript(
        """
        INSERT INTO restaurants(id,name,category,official_url) VALUES
          ('little-caesars','Little Caesars','pizza','https://littlecaesars.com');
        INSERT INTO branches(id,restaurant_id,address,city,state,zip,timezone) VALUES
          ('lc-detroit-40','little-caesars','530 East Warren, Detroit, MI 48201','Detroit','MI','48201','America/Detroit'),
          ('lc-houston-811','little-caesars','Houston, TX','Houston','TX',NULL,'America/Chicago');
        INSERT INTO menu_items(id,restaurant_id,name,category,size,serving_basis) VALUES
          ('lc-classic-cheese','little-caesars','Classic Cheese','pizza','Large','whole'),
          ('lc-classic-pepperoni','little-caesars','Classic Pepperoni','pizza','Large','whole'),
          ('lc-wings','little-caesars','Caesar Wings (8 pc)','wings','8 pieces','whole order');
        INSERT INTO sources(id,url,type,checked_at,reviewer) VALUES
          ('s-fresh','https://example.com/menu','ordering_menu', date('now'), 'tester'),
          ('s-stale','https://example.com/old','ordering_menu', date('now','-30 days'), 'tester');
        INSERT INTO price_snapshots(branch_id,item_id,channel,cents,source_id,checked_at,is_current) VALUES
          ('lc-detroit-40','lc-classic-cheese','pickup',549,'s-fresh',date('now'),1),
          ('lc-detroit-40','lc-classic-pepperoni','pickup',649,'s-stale',date('now','-30 days'),1),
          ('lc-houston-811','lc-classic-cheese','pickup',599,'s-fresh',date('now'),1);
        """
    )
    c.commit()
    yield c
    c.close()
