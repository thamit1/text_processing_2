# pip install transformers datasets seqeval scikit-learn

from datasets import Dataset
from transformers import BertTokenizerFast

tokenizer = BertTokenizerFast.from_pretrained("bert-base-uncased")

# Example data
examples = [
    {
        "tokens": ["3yr", "(USD)", "@", "MS+125bps", "area", "5yr", "(EUR)", "@", "MS+140bps", "area"],
        "labels":  ["B-TENOR", "B-CURRENCY", "O", "B-IPT", "O", "B-TENOR", "B-CURRENCY", "O", "B-IPT", "O"]
    }
]

# Convert to Hugging Face Dataset
dataset = Dataset.from_list(examples)

from transformers import BertForTokenClassification, Trainer, TrainingArguments

label_list = ["O", "B-TENOR", "B-CURRENCY", "B-IPT"]
id2label = {i: label for i, label in enumerate(label_list)}
label2id = {label: i for i, label in enumerate(label_list)}

model = BertForTokenClassification.from_pretrained("bert-base-uncased", num_labels=len(label_list), id2label=id2label, label2id=label2id)

training_args = TrainingArguments(
    output_dir="./parser_model",
    evaluation_strategy="no",
    per_device_train_batch_size=8,
    num_train_epochs=5,
    logging_steps=10
)

trainer = Trainer(
    model=model,
    args=training_args,
    train_dataset=dataset,
    tokenizer=tokenizer
)

trainer.train()
# Save the model and tokenizer

text = "10yr (GBP) @ MS+165bps area"
tokens = tokenizer.tokenize(text)
inputs = tokenizer(text, return_tensors="pt")
outputs = model(**inputs).logits.argmax(-1)
labels = [id2label[i] for i in outputs[0].tolist()]
print(list(zip(tokens, labels)))
trainer.save_model("./parser_model")
tokenizer.save_pretrained("./parser_model")
# The model and tokenizer are saved to the specified directory.
# The model can now be loaded later for inference or further training.
# The code above trains a BERT model for token classification on a custom dataset.
# The model can be used to predict labels for new text inputs.
# The tokenizer is also saved for tokenizing new inputs in the same way as during training.
