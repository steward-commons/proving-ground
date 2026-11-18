import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import memory_quiz, seal

class LetterAnswers(unittest.TestCase):
    def test_letter_maps_to_option_text(self):
        key = b"k" * 32
        item = {"id": "q1", "options": ["A) Rover", "B) Byte", "C) Goldie"],
                "hashes": [seal.answer_hmac(key, "q1", "Goldie")]}
        for ans in ["C", "c", "C)", "(C)", "Goldie"]:
            r = memory_quiz.grade([item], [ans], key=key)
            self.assertEqual(r["correct"], 1, ans)
        self.assertEqual(memory_quiz.grade([item], ["B"], key=key)["correct"], 0)
        self.assertEqual(memory_quiz.grade([item], ["Z"], key=key)["correct"], 0)

if __name__ == "__main__":
    unittest.main()
