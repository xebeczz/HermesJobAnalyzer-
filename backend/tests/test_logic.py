from app.main import match_job, norm_text, canonical_url

def test_normalizes_whitespace():
    assert norm_text('  Python\n developer  ') == 'Python developer'

def test_canonical_url_rejects_unsafe_scheme():
    assert canonical_url('javascript:alert(1)') is None
    assert canonical_url('https://EXAMPLE.com/jobs/') == 'https://example.com/jobs'

def test_matching_explains_missing_skills():
    profile={'skills':['Python','SQL'],'target_roles':['Python Developer'],'preferred_locations':['India'],'remote_preference':'any','education_level':'Undergraduate'}
    job={'title':'Python Developer Intern','location':'Bengaluru, India','description':'Required skills: Python, SQL, machine learning'}
    result=match_job(profile,job)
    assert result['score'] > 0
    assert 'python' in result['matched_skills']
    assert 'machine learning' in result['missing_skills']
    assert 'not a probability' in result['disclaimer']

def test_empty_profile_is_uncertain_not_perfect():
    result=match_job({'skills':[],'target_roles':[],'preferred_locations':[],'remote_preference':'any'}, {'title':'Engineer','location':'Not provided','description':''})
    assert result['confidence']=='limited'
    assert result['score'] < 100
