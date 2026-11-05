from src.core.story_context import StoryContext


def test_latest_story_replaces_old():
    c=StoryContext();c.add_input("Conte uma historia sobre castelo.");c.finish_input()
    c.add_output("Um castelo antigo")
    c.add_input("Conte uma historia sobre um astronauta.");c.finish_input()
    assert "astronauta" in c.context()
    assert "castelo" not in c.context()


def test_resume_and_unrelated_question_preserve_topic():
    c=StoryContext();c.add_input("Conte uma historia sobre castelo.");c.finish_input()
    c.add_input("Quanto e sete mais cinco?");c.finish_input()
    c.add_input("Volte a contar a historia.");c.finish_input()
    assert "castelo" in c.context()


def test_expiry_and_bounded_excerpt():
    now=[10];c=StoryContext(clock=lambda:now[0])
    c.add_input("Conte uma historia");c.finish_input();c.add_output("x"*10000)
    assert len(c.excerpt)==2500
    now[0]=911
    assert c.context()==""


def test_no_story_means_no_invented_context():
    c=StoryContext();c.add_input("Continue a historia");c.finish_input()
    assert c.context()==""


def test_math_answer_does_not_replace_story_excerpt():
    c=StoryContext();c.add_input("Conte uma historia sobre castelo");c.finish_input()
    c.add_output("Era um castelo")
    c.add_input("Quanto e sete mais cinco?");c.finish_input();c.add_output("Doze")
    assert c.excerpt=="Era um castelo"
