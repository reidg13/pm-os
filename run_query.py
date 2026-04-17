import os, sys
import snowflake.connector
from dotenv import load_dotenv

load_dotenv()

def run_query(query: str):
    conn = snowflake.connector.connect(
        user=os.getenv("SNOWFLAKE_USER"),
        account=os.getenv("SNOWFLAKE_ACCOUNT"),
        authenticator=os.getenv("SNOWFLAKE_AUTHENTICATOR", "snowflake"),
        warehouse=os.getenv("SNOWFLAKE_WAREHOUSE"),
        database=os.getenv("SNOWFLAKE_DATABASE"),
        schema=os.getenv("SNOWFLAKE_SCHEMA"),
    )
    cur = conn.cursor()
    cur.execute(query)
    cols = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return cols, rows

if __name__ == "__main__":
    import argparse
    import csv as csv_module

    parser = argparse.ArgumentParser()
    parser.add_argument("query", help="SQL query string or path to a .sql file")
    parser.add_argument("--csv", metavar="FILE", help="Write output to a CSV file")
    args = parser.parse_args()

    query = args.query
    if query.endswith(".sql") and os.path.exists(query):
        with open(query) as f:
            query = f.read()

    cols, rows = run_query(query)

    if args.csv:
        with open(args.csv, "w", newline="") as f:
            writer = csv_module.writer(f)
            writer.writerow(cols)
            writer.writerows(rows)
        print(f"Saved {len(rows)} rows to {args.csv}")
    else:
        print(" | ".join(cols))
        print("-" * 80)
        for row in rows:
            print(" | ".join(str(v) for v in row))
