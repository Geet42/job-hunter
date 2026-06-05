"""Quick test of all new scrapers."""
from dotenv import load_dotenv; load_dotenv()
from scraper import scrape_indeed, scrape_jobsie, scrape_irishjobs, scrape_lever

def show(jobs, n=3):
    for j in jobs[:n]:
        print(f"  [{j['source']}] {j['title']} @ {j['company']}")
        print(f"    url: {j['url'][:70]}")
    if not jobs:
        print("  (none)")

print("=== Testing new scrapers ===\n")

print("--- Indeed Ireland RSS ---")
show(scrape_indeed("software engineer intern", "Ireland", 5))

print("\n--- Jobs.ie ---")
show(scrape_jobsie("software engineer", "Ireland", 5))

print("\n--- IrishJobs.ie ---")
show(scrape_irishjobs("software engineer", "Ireland", 5))

print("\n--- Lever ATS ---")
show(scrape_lever("engineer intern graduate junior", "ireland", 10))
