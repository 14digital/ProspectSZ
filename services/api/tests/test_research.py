from bs4 import BeautifulSoup
from app.modules.research.site import candidates

def test_decision_maker_extracted_with_website_evidence_and_linkedin():
    html="""<section class='team-card'><h2>Susan Olueh</h2><p>Founder &amp; Managing Director</p>
    <a href='https://www.linkedin.com/in/susan-olueh'>LinkedIn</a></section>"""
    found=candidates(BeautifulSoup(html,"html.parser"),"https://example.com/meet-the-team")
    assert len(found)==1
    assert found[0].name=="Susan Olueh" and found[0].role=="Founder & Managing Director"
    assert found[0].source_url.endswith("meet-the-team") and found[0].linkedin_url.endswith("susan-olueh")

def test_generic_team_copy_does_not_invent_a_person():
    found=candidates(BeautifulSoup("<section><h2>Our Team</h2><p>Our managing director leads quality.</p></section>","html.parser"),"https://example.com/about")
    assert found==[]
