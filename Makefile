clean:
	-rm -f *.pyc sourcer/*.pyc tests/*.pyc

test: clean
	python -m tests.test_sourcer
	python -m tests.test_excel
