A confirmed mention means the paper explicitly names this resource (by its full name and/or abbreviation) and discusses it in a way consistent with the resource's known attributes above (e.g. its disease focus or data modality) - not merely a coincidental name match, a different resource with a similar acronym, or a passing citation to an unrelated study that happens to reference this one.

Output a JSON object with exactly these keys:
- "verification_status": one of "confirmed", "not_confirmed", or "insufficient_evidence".
- "claim_text": the exact sentence(s) from the paper that most directly support your verification_status. Use "n/a" if verification_status is "not_confirmed".
- "rationale": a brief (1-3 sentence) explanation, referencing which of the resource's attributes (name, abbreviation, disease focus, data modality) matched or mismatched.

Do not confirm a resource based on name similarity alone - check that the paper's described population, disease focus, or data modality is consistent with the resource's attributes. A resource mentioned only in passing (e.g. as related work, or to contrast with a different study) is "not_confirmed", not "confirmed".
