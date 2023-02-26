import os
import numpy as np
import random
import torch
import pandas as pd

from src.preprocessing import load_point_cloud

from torch.utils.data import Dataset

from transformers import BertTokenizer


class TextPointCloudDataset(Dataset):
    def __init__(self, root_dir, pc_transform=None, stage="train"):
        self.root_dir = root_dir
        self.stage = stage

        self.text_tokenizer = BertTokenizer.from_pretrained(
            "bert-base-uncased", do_lower_case=True
        )
        self.pc_transforms = pc_transform

        text_queries_folder_path = os.path.join(root_dir, "text_queries")

        ground_truth_path = os.path.join(
            text_queries_folder_path, "TextQuery_GT_Train.csv"
        )
        validation_ground_truth_path = os.path.join(
            text_queries_folder_path, "TextQuery_GT_Validation.csv"
        )
        text_queries_path = os.path.join(
            text_queries_folder_path, "TextQuery_Train.csv"
        )
        model_id_path = os.path.join(text_queries_folder_path, "ModelID.csv")

        self.point_cloud_path = os.path.join(root_dir, "PC_OBJ")

        self.ground_truth_csv = pd.read_csv(ground_truth_path, sep=";")
        self.validation_ground_truth_csv = pd.read_csv(
            validation_ground_truth_path, sep=";"
        )
        self.text_queries_csv = pd.read_csv(text_queries_path, sep=";")

        self.point_cloud_ids_list = pd.read_csv(model_id_path)["ID"].to_list()
        self.text_queries_mapping = dict(self.text_queries_csv.values)

        self.text_queries_list = self.ground_truth_csv["Text Query ID"].to_list()
        self.point_cloud_list = self.ground_truth_csv["Model ID"].to_list()

        self.validation_text_queries_list = self.validation_ground_truth_csv[
            "Text Query ID"
        ].to_list()
        self.validation_point_cloud_list = self.validation_ground_truth_csv[
            "Model ID"
        ].to_list()

        self.queries_model_mapping = dict()
        for i, text in enumerate(self.text_queries_list):
            if text not in self.queries_model_mapping:
                self.queries_model_mapping[text] = set()
            self.queries_model_mapping[text].add(self.point_cloud_list[i])

        print(self.validation_text_queries_list)
        print(self.validation_point_cloud_list)

    def _preprocess_pc(self, filename):
        pointcloud = load_point_cloud(filename)
        if self.pc_transforms:
            pointcloud = self.pc_transforms(pointcloud)
        return pointcloud

    def _preprocess_text(self, input_text):
        encoded_dict = self.text_tokenizer.encode_plus(
            input_text,
            add_special_tokens=True,
            max_length=64,
            pad_to_max_length=True,
            return_attention_mask=True,
            return_tensors="pt",
        )
        input_ids = torch.flatten(torch.tensor(encoded_dict["input_ids"]))
        attention_mask = torch.flatten(torch.tensor(encoded_dict["attention_mask"]))

        return input_ids, attention_mask

    def __len__(self):
        if self.stage == "train":
            return len(self.text_queries_list)
        else:
            return len(self.validation_text_queries_list)

    def __getitem__(self, idx):
        if self.stage == "train":
            text_queries_id = self.text_queries_list[idx]
            true_point_cloud_id = false_point_cloud_id = self.point_cloud_list[idx]
        else:
            text_queries_id = self.validation_text_queries_list[idx]
            true_point_cloud_id = (
                false_point_cloud_id
            ) = self.validation_point_cloud_list[idx]

        while false_point_cloud_id in self.queries_model_mapping[text_queries_id]:
            false_point_cloud_id = self.point_cloud_ids_list[
                random.randint(0, len(self.point_cloud_ids_list) - 1)
            ]
            # false_point_cloud_id = 'f770b7a17bed6938'

        # print(text_queries_id, true_point_cloud_id, false_point_cloud_id)
        text_sample = self.text_queries_mapping[text_queries_id]
        text_input_ids, text_attention_mask = self._preprocess_text(text_sample)

        true_pc_path = os.path.join(self.point_cloud_path, f"{true_point_cloud_id}.obj")
        false_pc_path = os.path.join(
            self.point_cloud_path, f"{false_point_cloud_id}.obj"
        )

        true_point_cloud = self._preprocess_pc(true_pc_path)
        false_point_cloud = self._preprocess_pc(false_pc_path)

        return {
            "true_point_cloud": true_point_cloud,
            "false_point_cloud": false_point_cloud,
            "input_ids": text_input_ids,
            "attention_mask": text_attention_mask,
        }

    def collate_fn(self, batch):
        batch_as_dict = {
            "true_point_clouds": torch.stack([x["true_point_cloud"] for x in batch])
            .float()
            .transpose(1, 2),
            "false_point_clouds": torch.stack([x["false_point_cloud"] for x in batch])
            .float()
            .transpose(1, 2),
            "text_queries": {
                "input_ids": torch.stack([x["input_ids"] for x in batch]),
                "attention_mask": torch.stack([x["attention_mask"] for x in batch]),
            },
        }

        return batch_as_dict
