"""The official Neo4j driver, talking to the committed Relate store over Bolt.

    relate serve --database data/relate-adr.rl --read-only --bolt 7687 --auth none &
    uv run --with neo4j python examples/bolt_driver.py [bolt://127.0.0.1:7687]

Nothing in Precedent depends on the Neo4j driver; this only shows that the graph it builds is an ordinary
Neo4j-protocol database to anything that speaks Bolt and Cypher.
"""

import sys

from neo4j import GraphDatabase

URI = sys.argv[1] if len(sys.argv) > 1 else "bolt://127.0.0.1:7687"

with GraphDatabase.driver(URI, auth=None) as driver:  # the server was started with --auth none (local use only)
    driver.verify_connectivity()
    print("connected to", driver.get_server_info().agent)
    with driver.session() as session:
        print("\nstanding of the 533 decisions")
        for rec in session.run("MATCH (d:Decision) RETURN d.standing AS standing, count(d) AS n ORDER BY n DESC"):
            print(f"  {rec['standing']:<9} {rec['n']}")
        print("\nwho overruled ADR-0116, and which clauses")
        for rec in session.run(
            "MATCH (a:Decision)-[t:SUPERSEDES {effective: true}]->(:Decision {id: 'ADR-0116'}) RETURN a.id AS decision, t.clauses AS clauses ORDER BY a.id"
        ):
            print(f"  {rec['decision']}  clauses {rec['clauses']}")
