# Copied from sdks/configuration.mdx by scripts/sync_doc_examples.py: do not edit by hand.

# --- sdks/configuration.mdx:12
from kardinal import Kardinal

k = Kardinal()  # api_key=None, base_url=None, timeout=30, max_retries=3


# --- sdks/configuration.mdx:65
who = k.whoami()
print(who.baseUrl, who.agencyId)
expected_agency = "A_sandbox"  # read it from your own configuration
if who.agencyId != expected_agency:
    raise RuntimeError(f"This API key belongs to {who.agencyId}, not to {expected_agency}")


# --- sdks/configuration.mdx:105
with Kardinal() as k:
    plans = k.routing.plans.list()

k = Kardinal()
plans = k.routing.plans.list()
k.close()
