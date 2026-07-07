.PHONY: generate solve redteam clean

generate:
	sage chall/gen.sage

solve:
	sage solve/solve.sage

redteam:
	sage chall/redteam.sage

clean:
	rm -f chall/private.json dist/output.json
	find . -name "*.sage.py" -delete
	find . -name "__pycache__" -type d -prune -exec rm -rf {} +

