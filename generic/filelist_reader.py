import os
import re


OPTION_PREFIX = "+-"
filelist_pattern = re.compile(r"\s*(-f|-F)?\s*(\S+)")


def iter_filelist_reader(filelist, _scope=0, parent=None, line_count=None):

    match = filelist_pattern.match(filelist)
    if not match:
        raise ValueError("input filelist format incorrect")
    filelist = match.group(2)

    if not os.path.exists(filelist):
        loc = " at line %s in %s" % (line_count, parent) if parent else ""
        raise OSError("The file '%s' does not exist%s" % (filelist, loc))

    yield filelist
    line_count = 0

    with open(filelist, "r") as fo:
        for line in fo.readlines():
            line_count += 1
            line = re.sub(
                r"//.*", "", line
            ).strip()  # remove comments and space between
            preceding_token = None
            if not line:
                continue
            tokens = re.split(r"\s*", line)

            for token in tokens:
                token = os.path.expandvars(token)
                if not token:
                    continue

                if preceding_token:
                    # mean current token could be option value
                    if preceding_token == "-f" or preceding_token == "-F":
                        for item in iter_filelist_reader(
                            token, _scope + 1, filelist, line_count
                        ):
                            yield item

                    elif token[0] not in OPTION_PREFIX:
                        yield token

                    preceding_token = None

                elif token[0] == "-":
                    # current token is a option
                    preceding_token = token

                elif token.startswith("+incdir"):
                    token = token.split("+")
                    for dir in token[2:]:
                        if dir:
                            yield dir
                elif token[0] not in OPTION_PREFIX:
                    yield token
