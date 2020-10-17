import glob
import exemplary


def test_docs():
    pathnames = glob.glob('**/*.md', recursive=True)
    exemplary.run(pathnames, render=False)
