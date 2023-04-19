#!/usr/bin/env python3

import os
import sys
import fnmatch
import tiktoken

def get_ignore_list(ignore_file_path):
    ignore_list = []
    with open(ignore_file_path, 'r') as ignore_file:
        for line in ignore_file:
            if sys.platform == "win32":
                line = line.replace("/", "\\")
            ignore_list.append(line.strip())
    return ignore_list

def should_ignore(file_path, ignore_list):
    for pattern in ignore_list:
        if fnmatch.fnmatch(file_path, pattern):
            return True
    return False

def get_token_count(string, model_name='gpt-4'):
    encoding = tiktoken.encoding_for_model(model_name)
    return len(encoding.encode(string))

def write_preamble(file, preamble_file=None):
    preamble_basic = "The following text contains relevant files and documentation from a Git repo. The text contains sections that begin with ----, followed by a single line containing the file path and file name, followed by a variable amount of lines containing the file contents. The end of each file is denoted by --END OF FILE--. The text representing the Git repository ends when the line --END-- is encounted. Any further text beyond --END-- is meant to be interpreted as instructions using the Git repository as context. The code may be provided in multiple entries, each of which will be denoted with a --PART #-- heading. Please remember all code beginning at --PART 1--, but don't respond until receiving an entry containing the --END-- line.\n"
    intro_count = get_token_count(preamble_basic, 'gpt-4')
    text_count = 0

    if preamble_file:
        with open(preamble_file, 'r') as pf:
            preamble_extra = pf.read()
            text_count = get_token_count(preamble_extra, 'gpt-4')
        file.write(f"{preamble_extra}\n{preamble_basic}\n\n\n\n***DATA START***\n\n-PART 1-\n\n")
    else:
        file.write(f"{preamble_basic}\n\n***DATA START***\n\n-PART 1-\n\n\n")
    return intro_count + text_count

def write_preamble_multiple(file, file_index):
    str = f"--PART {file_index}--\n\n\n"
    file.write(str)
    return get_token_count(str)

def close_output_file(file):
    file.write("--FILE END--")
    file.close()

def close_output_file_final(file):
    file.write("--END--\n\n***DATA STOP***")
    file.close()

def process_repository(repo_path, ignore_list, output_file_path, tokens_per_file=-1, preamble_path=None,
                       max_output_files=5):
    # Initialize output file index
    output_file_index = 1
    current_output_file = None
    token_count = 0

    global success
    success = 0

    for root, _, files in os.walk(repo_path):
        for file in files:
            file_path = os.path.join(root, file)
            relative_file_path = os.path.relpath(file_path, repo_path)

            if not should_ignore(relative_file_path, ignore_list):
                with open(file_path, 'r', errors='ignore') as file:
                    contents = file.read()

                    if tokens_per_file < 0:
                        # no token limit - write to a single file
                        output_file = open(f"{output_file_path}", "w")
                        output_file.write("-" * 4 + "\n")
                        output_file.write(f"{relative_file_path}\n")
                        output_file.write(f"{contents}\n")
                    else:
                        # use the given token limit, write to multiple files
                        output_file_base, output_file_extension = os.path.splitext(output_file_path)
                        output_path_with_index = f"{output_file_base}_{output_file_index}{output_file_extension}"

                        # if there's no file, create a new one
                        if not current_output_file:
                            print(f"\nWriting to file {output_path_with_index}")
                            current_output_file = open(output_path_with_index, "w")
                            token_count = get_token_count(contents, 'gpt-4') + write_preamble(current_output_file, preamble_path)

                        # if the new token count after written exceeds the limit, close the file and start a new one.
                        if (token_count) > tokens_per_file:
                            # Close the current output file if it exists and update the output file index
                            if current_output_file:
                                close_output_file(current_output_file)
                                success = 1
                                current_output_file = None

                            # Show the token count used
                            print(f"Wrote " + str(token_count) + f" tokens to file {output_file_base}_{output_file_index}{output_file_extension}.")

                            # Create a new output file
                            output_file_index += 1

                            # If the max file limit reached, skip
                            if output_file_index > max_output_files:
                                print("Max file limit reached. Quitting early.")
                                return output_file_index - 1

                            output_path_with_index = f"{output_file_base}_{output_file_index}{output_file_extension}"
                            output_file_base, output_file_extension = os.path.splitext(output_file_path)
                            current_output_file = open(f"{output_file_base}_{output_file_index}"
                                                       f"{output_file_extension}", "w")

                            print(f"\nWriting to file {output_path_with_index}")
                            token_count = write_preamble_multiple(current_output_file, output_file_index)

                        current_output_file.write("-" * 4 + "\n")
                        current_output_file.write(f"{relative_file_path}\n")
                        current_output_file.write(f"{contents}\n")
                        token_count += get_token_count(contents, 'gpt-4')

    # after iterating through all files, if there's an open file, close it
    if current_output_file:
        close_output_file_final(current_output_file)
        print(f"Wrote " + str(token_count) + f" tokens to file {output_file_base}_{output_file_index}{output_file_extension}.")
        success = 1

    return output_file_index

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python git_to_text.py /path/to/git/repository [-p /path/to/preamble.txt] [-o /path/to/output_file.txt]")
        sys.exit(1)

    repo_path = sys.argv[1]
    ignore_file_path = os.path.join(repo_path, ".gptignore")
    if sys.platform == "win32":
        ignore_file_path = ignore_file_path.replace("/", "\\")

    if not os.path.exists(ignore_file_path):
        # try and use the .gptignore file in the current directory as a fallback.
        HERE = os.path.dirname(os.path.abspath(__file__))
        ignore_file_path = os.path.join(HERE, ".gptignore")

    preamble_file = None
    if "-p" in sys.argv:
        preamble_file = sys.argv[sys.argv.index("-p") + 1]

    output_file_path = 'output.txt'
    if "-o" in sys.argv:
        output_file_path = sys.argv[sys.argv.index("-o") + 1]

    tokens_per_file = -1
    if "-t" in sys.argv:
        tokens_per_file = int(sys.argv[sys.argv.index("-t") + 1])

    max_output_files = 5
    if "-m" in sys.argv:
        max_output_files = int(sys.argv[sys.argv.index("-m") + 1])

    if os.path.exists(ignore_file_path):
        ignore_list = get_ignore_list(ignore_file_path)
    else:
        ignore_list = []

    output_file_index = process_repository(repo_path, ignore_list, output_file_path, tokens_per_file, preamble_file,
                                           max_output_files)

    # Display final message
    if success:
        print(f"\nRepository contents written to {output_file_index} file(s):")

        for i in range(1, output_file_index + 1):
            output_file_base, output_file_extension = os.path.splitext(output_file_path)
            output_path_with_index = f"{output_file_base}_{i}{output_file_extension}"
            print(f"  File {i}: {output_path_with_index}")
            
    else:
        print("\nNo files written.\n")
