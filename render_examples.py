import glob
import exemplary


def render_examples():
    pathnames = glob.glob('**/*.md', recursive=True)
    exemplary.run(pathnames, render=True)

if __name__ == '__main__':
    render_examples()
