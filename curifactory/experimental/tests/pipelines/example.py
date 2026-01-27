from curifactory.experimental.artifact import Artifact
from curifactory.experimental.pipeline import pipeline
from curifactory.experimental.stage import stage


@stage(Artifact("thing1"))
def get_thing1(start_num: int = 5):
    return start_num


@stage(Artifact("thing2"))
def get_thing2(thing1, next_num: int = 3):
    return thing1 + next_num


@pipeline
def add_things(num1: int = 2, num2: int = 7):
    t1 = get_thing1(num1).outputs
    t2 = get_thing2(t1, num2).outputs
    return t2


example1 = add_things("ex_one", num1=1, num2=2)
example2 = add_things("ex_two", num1=2, num2=3)
