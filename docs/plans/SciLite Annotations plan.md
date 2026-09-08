## SciLite Annotations

SciLite annotations are the annotations that appear in Europe PMC (in the order of 5*10^2 per article). These annotations were integrated   from different sources.
Trained expert curators read numerous scientific articles to annotate data with information, such as biological functions, molecular interactions and gene-disease associations. The International Society for Biocuration (ISB) (Bateman, 2010) was founded in 2009 to coordinate biocuration efforts.

### A long standing problem
A number of methods were developed to facilitate automated extraction of various article types and biological concepts, such as Textpresso (Müller et al., 2004), iHOP (Fernández et al., 2007), Whatizit (Rebholz-Schuhmann et al., 2008), EAGLi (Gobeill et al., 2009; Gobeill et al., 2015) EVEX (Landeghem & Ginter, 2011), PubTator (Wei et al., 2013) and Argo (Rak et al., 2014).

Annotations received from contributors are modelled according to the W3C standard Web Annotation Data Model (Text Quote Selector and the Fragment Selector)

### Limitations of the first version
The current process does not take into account false negatives, i.e. when an annotation was missed by an algorithm. A mechanism to handle false negatives would be a desirable future development.

### 2023 Update
Billions of annotations present.

### Schema Desiderata
  | Metadata element | Requirement for indexing |
  |---|---|
  | Preprint identifier (Crossref DOI required) | Essential |
  | Preprint title | Essential |
  | Author names | Essential |
  | Abstracts | Essential |
  | Publication date | Essential |
  | Author affiliations | Desired |
  | Links to peer-reviewed versions | Desired |
  | Licencing | Desired |
  | Funding | Desired |
  | Version information | Desired |
  | Withdrawal / removal status | Desired |
  │ Withdrawal / removal status                 │ Desired                  │
