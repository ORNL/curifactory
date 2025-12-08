# https://stackoverflow.com/questions/28094590/ignore-str-formatfoo-if-key-doesnt-exist-in-foo
class FailsafeDict(dict):
    def __getitem__(self, item):
        try:
            return super().__getitem__(item)
        except KeyError:
            return "{" + str(item) + "}"
