from sourcer import Grammar

g = Grammar(r'''
    start = List(Text | Section)

    Text = /([^`<]|\n|(`[^`])|(``[^`])|(<[^\!]))+/
    Section = VisibleSection | HiddenSection

    class VisibleSection {
        comment: InlineComment << "\n"
        python: PythonSection
    }

    class HiddenSection {
        open: StartComment
        tag: "HIDDEN TEST" << /[\s\n]*/
        body: /(.|\n)*?(?=\s*\-\-\>)/
        close: EndComment
    }

    class InlineComment {
        open: StartComment
        tag: /.*?(?=\s*\-\->)/
        close: EndComment
    }

    class PythonSection {
        open: "```python\n"
        body: /(.|\n)*?(?=```)/
        close: "```"
    }

    StartComment = /\<\!\-\-\s*/
    EndComment = /\s*\-\-\>/
''')


def parse_doc(contents):
    return g.parse(contents)
